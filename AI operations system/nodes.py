import json
from typing import Any, Dict, List

from model import OllamaQwenModel
from odoo_client import OdooClient

REQUIRED_FIELDS = {"name", "email", "phone", "tags", "property_type"}
# Nice-to-have — captured when mentioned, but never blocks creating the lead.
OPTIONAL_FIELDS = {
    "priority", "company_name", "street", "street2", "city", "country", "website",
}
ALL_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

VERIFY_OPERATION_PROMPT = """You are a real estate CRM assistant. You remember this \
conversation — use anything relevant said earlier (names, preferences, etc.).

Conversation so far:
{history}

Reply with ONLY this JSON shape, no extra text, no markdown fences:
{{
  "is_operation": true | false,
  "reply": "<string>",
  "entities": {{"name": <string|null>, "email": <string|null>, "phone": <string|null>, "tags": <string|null>, "property_type": <string|null>, "priority": <string|null>, "company_name": <string|null>, "street": <string|null>, "street2": <string|null>, "city": <string|null>, "country": <string|null>, "website": <string|null>}}
}}

"is_operation" = true only if the latest message asks to create/manage a CRM lead (mentions a \
client, a property, buying/selling/renting, or contact details). Otherwise false — greetings, \
small talk, questions, anything a general assistant would just answer.

If false: "reply" = a short, friendly chat reply (may mention you can also create leads); every \
entity null.
If true: "reply" = ""; fill "entities" using ONLY information literally stated (latest message \
or history above) — "tags" must be "buy"/"sell"/"rent", "property_type" must be \
"villa"/"house"/"apartment", "priority" must be "0"/"1"/"2"/"3" (shown to the user as 0-3 \
stars — map a star count directly, e.g. "two stars" -> "2"; "urgent"/"very important" -> "3"; \
"important"/"high priority" -> "2"; "low priority" -> "0"). company_name/street/street2/city/\
country/website are plain text, filled only if stated. Never invent or guess; anything not \
explicitly stated MUST be null.

Example: "create a lead for Sarah, she wants to rent an apartment, high priority" -> {{"is_operation": true, "reply": "", "entities": {{"name": "Sarah", "email": null, "phone": null, "tags": "rent", "property_type": "apartment", "priority": "2"}}}}

Latest message: {raw_text}

JSON:"""

CLARIFICATION_PROMPT = """You are a CRM assistant gathering lead details, chatting directly \
with the user — "message" below is sent to them as-is, not a description of your actions.

Conversation so far:
{history}

Required fields: name, email, phone, tags (buy/sell/rent), property_type (villa/house/apartment).
Optional fields (never block completion, only fill if the reply states them): priority \
("0"/"1"/"2"/"3", shown as 0-3 stars — "two stars"->"2", "urgent"->"3", "high priority"->"2", \
"low priority"->"0"); company_name; street; street2; city; country; website.
Already known: {known_entities}
Still missing (required): {missing_fields}
User's latest reply: "{raw_text}"

For each missing required field: if the reply literally states it, extract it exactly; if the \
reply tells you to fill it in yourself (e.g. "you decide", "make it up"), invent a reasonable \
value; otherwise leave it out. Also extract any optional fields above into filled_entities if \
the reply mentions them.

Reply with ONLY this JSON shape, no extra text, no markdown fences:
{{
  "filled_entities": {{"<field>": "<value>", ...}},
  "message": "<chat reply to send the user>"
}}
"filled_entities" only holds fields you extracted or invented — omit any still missing.
"message": if fields are still missing after this, ask for them BY NAME, specifically (mention \
they can say "you decide" for the rest); if nothing is missing, briefly confirm what you have.

JSON:"""


def _format_history(history: List[Dict[str, Any]]) -> str:
    """Render prior turns as a plain-text transcript for the LLM to read as context."""
    if not history:
        return "(no earlier messages)"
    speakers = {"user": "User", "assistant": "Assistant"}
    return "\n".join(
        f"{speakers.get(turn.get('role'), 'User')}: {turn.get('content', '')}"
        for turn in history
    )


def verify_operation(state: Dict[str, Any]) -> Dict[str, Any]:
    """Classify the message and, if it's an operation request, extract entities — in a single \
    LLM call, so a normal chat message doesn't pay for a second round-trip."""
    model = OllamaQwenModel()
    prompt = VERIFY_OPERATION_PROMPT.format(
        history=_format_history(state.get("history", [])),
        raw_text=state["raw_text"],
    )
    output_text = model.inference(prompt).strip()

    try:
        parsed = json.loads(_strip_code_fence(output_text))
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    is_operation = bool(parsed.get("is_operation"))

    if not is_operation:
        reply = parsed.get("reply") or "Hi! Let me know whenever you'd like to create a lead."
        return {"is_operation": False, "final_message": reply}

    raw_entities = parsed.get("entities") or {}
    entities = {
        field: value
        for field, value in raw_entities.items()
        if field in ALL_FIELDS and value
    }

    return {
        "is_operation": True,
        "intent": "create_lead",
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
        history=_format_history(state.get("history", [])),
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
    filled = {field: value for field, value in filled.items() if field in ALL_FIELDS and value}
    message = parsed.get("message") or "I need more information before creating the lead."

    entities = {**entities, **filled}
    still_missing = [field for field in REQUIRED_FIELDS if not entities.get(field)]

    return {
        "entities": entities,
        "missing_fields": still_missing,
        "is_valid": len(still_missing) == 0,
        "clarification_prompt": message,
    }


def _resolve_tag_id(env: Any, client: "OdooClient | None", tag_name: str) -> int:
    """Find (or create) the crm.tag matching a buy/sell/rent label."""
    label = tag_name.strip().capitalize()
    domain = [("name", "=", label)]
    if env is not None:
        tag = env["crm.tag"].search(domain, limit=1)
        return tag.id if tag else env["crm.tag"].create({"name": label}).id
    return client.find_or_create_id("crm.tag", domain, {"name": label})


def _resolve_country_id(env: Any, client: "OdooClient | None", country_name: str):
    """Best-effort lookup of a country by (partial) name — never invented, just matched."""
    domain = [("name", "ilike", country_name.strip())]
    if env is not None:
        country = env["res.country"].search(domain, limit=1)
        return country.id if country else False
    return client.find_id("res.country", domain) or False


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

    # Called from inside a running Odoo process (the wizard): use the ORM
    # directly via `env`. Going out over XML-RPC to this same server instead
    # would create the lead in a separate transaction that — under Odoo's
    # REPEATABLE READ isolation — this transaction can't see yet, causing a
    # foreign-key error when linking back to it. The standalone CLI script
    # has no `env`, so it falls back to a real XML-RPC client.
    env = state.get("env")
    client = None if env is not None else OdooClient()

    vals = {
        "name": f"{tags} - {property_type} - {contact_name}",
        "contact_name": contact_name,
        "email_from": entities.get("email"),
        "phone": entities.get("phone"),
        "description": f"Operation: {tags}\nProperty type: {property_type}",
        "tag_ids": [(6, 0, [_resolve_tag_id(env, client, tags)])],
    }
    optional_direct_fields = {
        "priority": "priority",
        "company_name": "partner_name",
        "street": "street",
        "street2": "street2",
        "city": "city",
        "website": "website",
    }
    for field, odoo_field in optional_direct_fields.items():
        if entities.get(field):
            vals[odoo_field] = entities[field]
    if entities.get("country"):
        country_id = _resolve_country_id(env, client, entities["country"])
        if country_id:
            vals["country_id"] = country_id

    if env is not None:
        lead_id = env["crm.lead"].create(vals).id
    else:
        lead_id = client.create_lead(vals)

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
    priority_labels = {"0": "low", "1": "medium", "2": "high", "3": "very high"}
    priority = entities.get("priority")
    priority_ref = f", {priority_labels.get(priority, priority)} priority" if priority else ""

    message = (
        f"Created lead for {name} ({phone}) who wants to {tags} {article} {property_type}"
        f"{priority_ref}{lead_ref}. I recorded the request and will continue with the CRM flow."
    )
    return {"final_message": message}
