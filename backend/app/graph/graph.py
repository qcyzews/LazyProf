# backend/app/graph/graph.py
import asyncio
from typing import List
from langgraph.graph import StateGraph, END, START
from langgraph.types import Send
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.graph.state import GraphState, PaperAnalysis, ArticleInput
from app.services.pdf_service import download_and_extract_pdf_text  # Twoja funkcja do PDF

# Inicjalizacja modelu Gemini 1.5 Pro / Flash
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.2)

# --- WĘZEŁ 1: Przetwarzanie Pojedynczego Artykułu (Faza MAP) ---
async def analyze_single_paper_node(state_item: dict) -> dict:
    article: ArticleInput = state_item["article"]
    user_instruction: str = state_item["user_instruction"]

    # 1. Pobranie i ekstrakcja tekstu z PDF
    pdf_text = await download_and_extract_pdf_text(article.pdf_url)

    # 2. Precyzyjna analiza przez Gemini z ustrukturyzowanym wyjściem (Structured Output)
    structured_llm = llm.with_structured_output(PaperAnalysis)
    
    prompt = f"""
    Analyze the following research paper titled '{article.title}' (arXiv ID: {article.arxiv_id}).
    
    User Specific Focus/Instruction:
    {user_instruction}
    
    Paper Content:
    {pdf_text[:30000]}  # Ograniczenie lub pełen tekst w zależności od potrzeb
    """
    
    analysis: PaperAnalysis = await structured_llm.ainvoke(prompt)
    analysis.arxiv_id = article.arxiv_id
    analysis.title = article.title

    # Zwracamy słownik, który zaktualizuje pole `individual_analyses` w stanie głównym
    return {"individual_analyses": [analysis]}


# --- KROK MAPUJĄCY: Dynamiczne Rozgałęzienie (Fan-out) ---
def map_articles_to_nodes(state: GraphState):
    """
    Dla każdego artykułu na liście tworzy oddzielną, równoległą instancję węzła analyze_single_paper_node.
    """
    return [
        Send("analyze_single_paper", {
            "article": article,
            "user_instruction": state["user_instruction"]
        })
        for article in state["articles"]
    ]


# --- WĘZEŁ 2: Synteza Raportu (Faza REDUCE) ---
async def synthesize_report_node(state: GraphState) -> dict:
    analyses: List[PaperAnalysis] = state["individual_analyses"]
    user_instruction: str = state["user_instruction"]

    # Przygotowanie kontekstu ze wszystkich równoległych analiz
    context = ""
    for a in analyses:
        context += f"\n### Paper: {a.title} ({a.arxiv_id})\n"
        context += f"- **Summary:** {a.summary}\n"
        context += f"- **Methodology:** {a.methodology}\n"
        context += f"- **Key Findings:** {', '.join(a.key_findings)}\n"
        context += f"- **Limitations:** {', '.join(a.limitations)}\n"

    synthesis_prompt = f"""
    You are an expert academic research assistant.
    Generate a comprehensive comparative synthesis report in Markdown format based on the analyzed papers below.

    User Objective:
    {user_instruction}

    Extracted Analyses from Individual Papers:
    {context}

    Requirements for the Markdown Output:
    1. **Title & Executive Summary**
    2. **Comparative Matrix / Table**: Include columns for Paper Title, Key Methodology, Main Strengths, and Limitations.
    3. **In-depth Synthesis**: Detailed analysis addressing the user's objective.
    4. **Critical Discussion & Future Directions**
    5. **References**: List with arXiv IDs and titles.

    Format the output cleanly in raw Markdown.
    """

    response = await llm.ainvoke(synthesis_prompt)
    return {"final_report": response.content}


# --- BUDOWANIE GRAFU ---
workflow = StateGraph(GraphState)

# Dodanie węzłów
workflow.add_node("analyze_single_paper", analyze_single_paper_node)
workflow.add_node("synthesize_report", synthesize_report_node)

# Definicja krawędzi (Edges)
# Z punktu START rozgałęziamy się dynamicznie na N równoległych węzłów mapujących
workflow.add_conditional_edges(START, map_articles_to_nodes, ["analyze_single_paper"])

# Gdy WSZYSTKIE równoległe analizy się zakończą, przechodzimy do węzła syntezy (Fan-in)
workflow.add_edge("analyze_single_paper", "synthesize_report")
workflow.add_edge("synthesize_report", END)

# Kompilacja grafu
app_graph = workflow.compile()