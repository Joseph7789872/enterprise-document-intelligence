"""LangGraph workflow definition.

Wires the runner's nodes into the multi-agent graph:

    planner → retriever → verifier ─┬─(low confidence / confidentiality)→ human_review → END
                                    └─(ok)→ synthesizer → source_attributor → END

The compiled graph is the canonical non-streaming path. The streaming endpoint reuses
the same ``WorkflowRunner`` methods up to the routing decision, then streams synthesis
directly (no checkpointer — agent state holds decrypted text and is never persisted).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import WorkflowRunner, route_after_verify
from app.agents.state import AgentState


def build_workflow(runner: WorkflowRunner):  # type: ignore[no-untyped-def]
    """Compile the agent graph bound to a request-scoped runner."""
    graph = StateGraph(AgentState)

    graph.add_node("planner", runner.planner)
    graph.add_node("retriever", runner.retriever)
    graph.add_node("verifier", runner.verifier)
    graph.add_node("human_review", runner.human_review)
    graph.add_node("synthesizer", runner.synthesizer)
    graph.add_node("source_attributor", runner.source_attributor)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "verifier")
    graph.add_conditional_edges(
        "verifier",
        route_after_verify,
        {"human_review": "human_review", "synthesizer": "synthesizer"},
    )
    graph.add_edge("synthesizer", "source_attributor")
    graph.add_edge("source_attributor", END)
    graph.add_edge("human_review", END)

    return graph.compile()
