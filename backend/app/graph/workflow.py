# /backend/app/graph/workflow.py
from langgraph.graph import END, START, StateGraph
import app.graph.nodes as nodes
from app.graph.state import MultiPaperState


def create_workflow():
    builder = StateGraph(MultiPaperState)

    # Rejestracja węzłów poprzez moduł nodes (dzięki temu @patch zadziała)
    builder.add_node("fetch_papers", nodes.fetch_papers_node)
    builder.add_node("generate_synthesis", nodes.generate_synthesis_node)
    builder.add_node("python_verifier", nodes.python_verifier_node)
    builder.add_node("llm_judge", nodes.llm_judge_node)
    builder.add_node("record_failed_attempt", nodes.record_failed_attempt_node)
    builder.add_node("format_final_report", nodes.format_final_report_node)

    # Krawędzie statyczne
    builder.add_edge(START, "fetch_papers")
    builder.add_edge("fetch_papers", "generate_synthesis")
    builder.add_edge("generate_synthesis", "python_verifier")
    builder.add_edge("python_verifier", "llm_judge")

    # Krawędzie warunkowe
    builder.add_conditional_edges(
        "llm_judge",
        nodes.decide_next_step,
        {
            "record_and_retry": "record_failed_attempt",
            "record_and_format": "record_failed_attempt",
            "format_report": "format_final_report",
        },
    )

    builder.add_conditional_edges(
        "record_failed_attempt",
        lambda state: (
            "format_final_report"
            if state.get("retry_count", 0) >= 3
            else "generate_synthesis"
        ),
        {
            "format_final_report": "format_final_report",
            "generate_synthesis": "generate_synthesis",
        },
    )

    builder.add_edge("format_final_report", END)

    return builder.compile()


# Domyślna instancja dla aplikacji
app_graph = create_workflow()