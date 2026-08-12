import json
from typing import Any, Dict, List

from model import OllamaQwenModel
from odoo_client import OdooClient

REQUIRED_FIELDS = {"name", "email", "phone", "tags", "property_type"}

INTENT_PROMPT = """You are an intent parser for a real estate CRM assistant. Read the user's \
message and respond with ONLY a JSON object (no extra text, no markdown fences) in this exact \
shape:
{{
  "intent": "create_lead" | "unknown",
  "entities": {{
    "name": <string or null>,
    "email": <string or null>,
    "phone": <string or null>,
    "tags": <string or null>,
    "property_type": <string or null>
  }}
}}
Field meanings:
- "tags": the type of operation the client wants — must be one of "buy", "sell", or "rent".
- "property_type": the kind of property involved — must be one of "villa", "house", or \
"apartment".

IMPORTANT: Only use information that is literally present in the user's message. Never \
invent, guess, or make up a name, email, phone number, tag, or property type. If a field is \
not explicitly mentioned, its value MUST be null — do not fill it with an example or \
placeholder value.

Example:
User message: create a lead for Sarah, she wants to rent an apartment
JSON: {{"intent": "create_lead", "entities": {{"name": "Sarah", "email": null, "phone": null, "tags": "rent", "property_type": "apartment"}}}}

User message: {raw_text}

JSON:"""

CLARIFICATION_PROMPT = """You are a CRM assistant creating a lead. You are talking directly \
to the end user in a chat — whatever you put in "message" below is sent to them as-is, so \
write it as a message TO them, not a description of what you're doing.

Required fields: name, email, phone, tags, property_type.
Field meanings: "tags" is the type of operation ("buy", "sell", or "rent"); "property_type" \
is the kind of property ("villa", "house", or "apartment").
Fields already known: {known_entities}
Fields still missing: {missing_fields}
The user's original message was: "{raw_text}"

Decide one of two things:
1. If the user's message suggests they want you to fill in the missing details yourself \
(e.g. "you decide", "fill it in for me", "whatever you think", "just make it up"), invent \
reasonable values for EVERY missing field, and write "message" as a short note TO the user \
confirming what you filled in on their behalf.
2. Otherwise, invent nothing, and write "message" as a short, friendly question TO the user, \
asking them directly to provide the missing fields (you may also mention they can tell you \
to fill the fields in yourself instead).

Respond with ONLY a JSON object (no extra text, no markdown fences) in this exact shape:
{{
  "filled_entities": {{"<field>": "<value>", ...}},
  "message": "<the exact chat message to send to the user>"
}}
If asking for clarification, "filled_entities" must be an empty object.
If filling values in, "filled_entities" must contain a value for every missing field.

JSON:"""


def parse_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Parse raw input into an intent and entity map using the LLM."""
    model = OllamaQwenModel()
    prompt = INTENT_PROMPT.format(raw_text=state["raw_text"])
    output_text = model.inference(prompt).strip()

    try:
        parsed = json.loads(_strip_code_fence(output_text))
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    intent = parsed.get("intent") or "unknown"
    raw_entities = parsed.get("entities") or {}
    entities = {
        field: value
        for field, value in raw_entities.items()
        if field in REQUIRED_FIELDS and value
    }

    return {
        "intent": intent,
        "entities": entities,
        "missing_fields": [],
    }


def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` fences some models wrap their output in."""
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def validate(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the parsed state and identify any missing required fields."""
    entities = state.get("entities", {})
    missing: List[str] = []

    for field in REQUIRED_FIELDS:
        value = entities.get(field)
        if not value:
            missing.append(field)

    state["missing_fields"] = missing
    state["is_valid"] = len(missing) == 0
    return state


def ask_clarification(state: Dict[str, Any]) -> Dict[str, Any]:
    """Let the LLM either fill in missing fields itself or ask the user for them."""
    missing = state.get("missing_fields", [])
    if not missing:
        return {"clarification_prompt": ""}

    entities = state.get("entities", {})
    model = OllamaQwenModel()
    prompt = CLARIFICATION_PROMPT.format(
        known_entities=entities,
        missing_fields=", ".join(missing),
        raw_text=state.get("raw_text", ""),
    )
    output_text = model.inference(prompt).strip()

    try:
        parsed = json.loads(_strip_code_fence(output_text))
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    filled = parsed.get("filled_entities") or {}
    filled = {field: value for field, value in filled.items() if field in REQUIRED_FIELDS and value}
    message = parsed.get("message") or "I need more information before creating the lead."

    entities = {**entities, **filled}
    still_missing = [field for field in REQUIRED_FIELDS if not entities.get(field)]

    return {
        "entities": entities,
        "missing_fields": still_missing,
        "is_valid": len(still_missing) == 0,
        "clarification_prompt": message,
    }


def execute_action(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the selected action against Odoo using the current state."""
    action = state.get("intent")
    entities = state.get("entities", {})

    if action != "create_lead":
        state["tool_result"] = {"action": action, "entities": entities}
        return state

    contact_name = entities.get("name")
    tags = entities.get("tags")
    property_type = entities.get("property_type")

    vals = {
        "name": f"{tags} - {property_type} - {contact_name}",
        "contact_name": contact_name,
        "email_from": entities.get("email"),
        "phone": entities.get("phone"),
        "description": f"Operation: {tags}\nProperty type: {property_type}",
    }

    lead_id = OdooClient().create_lead(vals)

    state["tool_result"] = {
        "action": action,
        "entities": entities,
        "lead_id": lead_id,
    }
    return state


def respond(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build the user-facing confirmation or clarification message."""
    if not state.get("is_valid"):
        message = state.get("clarification_prompt", "Missing required information.")
        return {"final_message": message}

    result = state.get("tool_result", {})
    entities = result.get("entities", {})
    name = entities.get("name", "unknown")
    phone = entities.get("phone", "unknown")
    tags = entities.get("tags", "unspecified")
    property_type = entities.get("property_type", "unspecified")
    article = "an" if property_type[:1].lower() in "aeiou" else "a"
    lead_id = result.get("lead_id")
    lead_ref = f" (Odoo lead #{lead_id})" if lead_id else ""

    message = (
        f"Created lead for {name} ({phone}) who wants to {tags} {article} {property_type}{lead_ref}. "
        f"I recorded the request and will continue with the CRM flow."
    )
    return {"final_message": message}
