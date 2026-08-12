from langgraph.graph import END, StateGraph

from nodes import ask_clarification, execute_action, parse_intent, respond, validate
from state import AgentState


def route_after_validate(state: AgentState) -> str:
    return "execute_action" if state["is_valid"] else "ask_clarification"


def route_after_clarification(state: AgentState) -> str:
    return "execute_action" if state["is_valid"] else "respond"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("parse_intent", parse_intent)
    graph.add_node("validate", validate)
    graph.add_node("execute_action", execute_action)
    graph.add_node("ask_clarification", ask_clarification)
    graph.add_node("respond", respond)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "validate")
    graph.add_conditional_edges("validate", route_after_validate)
    graph.add_conditional_edges("ask_clarification", route_after_clarification)
    graph.add_edge("execute_action", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


app = build_graph()


if __name__ == "__main__":
    user_input = input("You: ")
    result = app.invoke({"raw_text": user_input})

    print("\n--- LLM parsed output ---")
    print("Intent:", result["intent"])
    print("Entities:", result["entities"])

    print("\n--- Final response ---")
    print(result["final_message"])
