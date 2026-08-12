from typing import TypedDict

class AgentState(TypedDict, total=False):
    raw_text: str
    intent: str
    entities: dict
    missing_fields: list[str]
    is_valid: bool
    clarification_prompt: str
    tool_result: dict
    final_message: str
