from typing import Any, TypedDict

class AgentState(TypedDict, total=False):
    raw_text: str
    history: list[dict]
    env: Any  # only present when called from inside Odoo (the wizard), not the standalone CLI
    is_operation: bool
    intent: str
    entities: dict
    missing_fields: list[str]
    is_valid: bool
    clarification_prompt: str
    tool_result: dict
    final_message: str
