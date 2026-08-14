# /backend/app/graph/workflow.py
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    decide_next_step,
    expand_query_node,
    fetch_papers_node,
    format_final_report_node,
    generate_synthesis_node,
    llm_judge_node,
    python_verifier_node,
    record_failed_attempt_node,
)
from app.graph.state import MultiPaperState

builder = StateGraph(MultiPaperState)

# Rejestracja węzłów
builder.add_node("expand_query", expand_query_node)
builder.add_node("fetch_papers", fetch_papers_node)
builder.add_node("generate_synthesis", generate_synthesis_node)
builder.add_node("python_verifier", python_verifier_node)
builder.add_node("llm_judge", llm_judge_node)
builder.add_node("record_failed_attempt", record_failed_attempt_node)
builder.add_node("format_final_report", format_final_report_node)

# Definicja krawędzi statycznych
builder.add_edge(START, "expand_query")
builder.add_edge("expand_query", "fetch_papers")
builder.add_edge("fetch_papers", "generate_synthesis")
builder.add_edge("generate_synthesis", "python_verifier")
builder.add_edge("python_verifier", "llm_judge")

# Definicja krawędzi warunkowych
builder.add_conditional_edges(
    "llm_judge",
    decide_next_step,
    {
        "record_and_retry": "record_failed_attempt",
        "record_and_format": "record_failed_attempt",
        "format_report": "format_final_report",
    }
)

builder.add_conditional_edges(
    "record_failed_attempt",
    lambda state: "format_final_report" if state.get("retry_count", 0) >= 3 else "generate_synthesis",
    {
        "format_final_report": "format_final_report",
        "generate_synthesis": "generate_synthesis"
    }
)

builder.add_edge("format_final_report", END)

# Kompilacja grafu
multi_paper_graph = builder.compile()