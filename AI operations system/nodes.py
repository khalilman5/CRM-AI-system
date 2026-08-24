import json
from typing import Any, Dict, List

from model import OllamaQwenModel
from odoo_client import OdooClient

# The only thing that ever blocks creating a lead. Everything else below is
# best-effort: captured per-customer when mentioned, never blocks creation.
OPTIONAL_FIELDS = {
    "email", "phone", "tags", "property_type", "priority", "company_name",
    "street", "street2", "city", "country", "website", "notes",
}
ALL_FIELDS = OPTIONAL_FIELDS | {"name"}
OPERATION_TAGS = {"buy", "sell", "rent"}
PROPERTY_TAGS = {"villa", "house", "apartment"}

# operation is a discriminator: "create", "delete", "update" today, more can be added later
# by (1) adding the name here in the prompt, (2) teaching verify_operation what payload shape
# that operation extracts, (3) adding a branch in the wizard's dispatch.
OPERATIONS = {"create", "delete", "update"}

VERIFY_OPERATION_PROMPT = """Real estate CRM assistant. Remembers this conversation.

History:
{history}

Reply with ONLY this JSON, no extra text. Omit any field you'd otherwise set to null.
{{
  "is_operation": true|false,
  "operation": "create"|"delete"|"update",
  "reply": "<string>",
  "leads": [{{"name":<str>,"email":<str>,"phone":<str>,"tags":<str>,"property_type":<str>,"priority":<str>,"company_name":<str>,"street":<str>,"street2":<str>,"city":<str>,"country":<str>,"website":<str>,"notes":<str>}}],
  "delete_filters": [{{"name":<str>,"tags":<str>,"property_type":<str>}}],
  "update_filters": [{{"criteria":{{"name":<str>,"tags":<str>,"property_type":<str>}},"updates":{{"name":<str>,"email":<str>,"phone":<str>,"tags":<str>,"property_type":<str>,"priority":<str>,"company_name":<str>,"street":<str>,"street2":<str>,"city":<str>,"country":<str>,"website":<str>,"notes":<str>}}}}]
}}

is_operation=true if the message manages a lead in ANY way, any verb — create/add/register/\
log a client, a client buying/selling/renting, contact info given, delete/remove/cancel a \
lead, or change/update/edit/correct something about an existing lead. Else false: \
reply=short friendly chat, leads=[], delete_filters=[], update_filters=[], operation="create".

If true, pick ONE operation:
"delete" if explicitly asked to delete/remove/cancel. delete_filters = one object per \
deletion request, with whichever of name/tags/property_type is stated (omit the rest). \
leads=[], update_filters=[].
"update" if asked to change/edit/correct something about lead(s) that (implicitly) already \
exist, rather than describing a brand-new customer. update_filters = one object per update \
request: "criteria" = whichever of name/tags/property_type identifies WHICH lead(s) (same \
rules as delete), "updates" = whichever fields should CHANGE, with their NEW values (same \
field meanings as "leads" below). leads=[], delete_filters=[].
For BOTH delete and update: identify WHICH lead(s) using ONLY name/tags/property_type as \
literally stated in the latest message — NEVER guess or recall who matches from the \
conversation history above, a real database lookup does that separately once you've \
extracted the criteria.
"create" otherwise (default). leads = one entry per distinct customer mentioned, using ONLY \
info stated for them. Only "name" matters — everything else is optional, never blocks. tags: \
buy/sell/rent. property_type: villa/house/apartment. priority: "0"-"3" (0-3 stars — "two \
stars"->"2", "urgent"->"3", "high priority"->"2", "low priority"->"0"). notes = anything else \
worth keeping (budget, timeline, likes/dislikes), summarized briefly. Never invent or guess.

Examples:
"create a lead for Sarah, rent an apartment, high priority" -> {{"is_operation":true,"operation":"create","reply":"","leads":[{{"name":"Sarah","tags":"rent","property_type":"apartment","priority":"2"}}],"delete_filters":[],"update_filters":[]}}
"add a client Omar, wants to buy a house" -> {{"is_operation":true,"operation":"create","reply":"","leads":[{{"name":"Omar","tags":"buy","property_type":"house"}}],"delete_filters":[],"update_filters":[]}}
"delete the lead for Ahmed" -> {{"is_operation":true,"operation":"delete","reply":"","leads":[],"delete_filters":[{{"name":"Ahmed"}}],"update_filters":[]}}
"delete whoever wants to sell an apartment" -> {{"is_operation":true,"operation":"delete","reply":"","leads":[],"delete_filters":[{{"tags":"sell","property_type":"apartment"}}],"update_filters":[]}}
"change Ahmed's phone to 0612345678" -> {{"is_operation":true,"operation":"update","reply":"","leads":[],"delete_filters":[],"update_filters":[{{"criteria":{{"name":"Ahmed"}},"updates":{{"phone":"0612345678"}}}}]}}
"set everyone who wants to buy a villa to high priority" -> {{"is_operation":true,"operation":"update","reply":"","leads":[],"delete_filters":[],"update_filters":[{{"criteria":{{"tags":"buy","property_type":"villa"}},"updates":{{"priority":"2"}}}}]}}

Message: {raw_text}

JSON:"""

# Fires only once we already have a customer with everything except a name —
# a narrow extraction task, so it skips history/message-writing entirely and
# just asks the model to interpret one reply about one missing name.
NAME_PROMPT = """Customer missing a name. Known: {known_entities}
Reply: "{raw_text}"

If the reply states a name, extract it. If told to invent one ("you decide", "make it up"), \
invent a placeholder. If told there's no name / to leave it blank ("don't have it", \
"unknown", "N/A"), set skip_name=true. Else omit "name" and leave skip_name=false.
Also extract any of email/phone/tags(buy/sell/rent)/property_type(villa/house/apartment)/\
priority(0-3)/company_name/street/street2/city/country/website/notes if the reply mentions \
them for this customer — never invent those, only the name can be invented.

Reply with ONLY this JSON, no extra text. Omit any field you'd otherwise set to null.
{{"name":<str>,"skip_name":true|false,"email":<str>,"phone":<str>,"tags":<str>,"property_type":<str>,"priority":<str>,"company_name":<str>,"street":<str>,"street2":<str>,"city":<str>,"country":<str>,"website":<str>,"notes":<str>}}

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


def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` fences some models wrap their output in."""
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def verify_operation(state: Dict[str, Any]) -> Dict[str, Any]:
    """Classify the message: is it about a lead at all, and if so, which operation (create, \
    delete, ...) and its payload — in a single LLM call, so a normal chat message doesn't pay \
    for a second round-trip."""
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
        reply = parsed.get("reply") or "Hi! Let me know whenever you'd like to add or remove a lead."
        return {"is_operation": False, "final_message": reply}

    operation = parsed.get("operation")
    if operation not in OPERATIONS:
        operation = "create"

    if operation == "delete":
        filters = [
            criteria
            for raw_filter in (parsed.get("delete_filters") or [])
            if (criteria := _clean_dict(raw_filter, ("name", "tags", "property_type")))
        ]
        return {"is_operation": True, "operation": "delete", "delete_filters": filters}

    if operation == "update":
        updates_list = []
        for raw_filter in parsed.get("update_filters") or []:
            criteria = _clean_dict((raw_filter or {}).get("criteria"), ("name", "tags", "property_type"))
            updates = _clean_dict((raw_filter or {}).get("updates"), ALL_FIELDS)
            if criteria and updates:
                updates_list.append({"criteria": criteria, "updates": updates})
        return {"is_operation": True, "operation": "update", "update_filters": updates_list}

    leads = [
        lead
        for raw_lead in (parsed.get("leads") or [])
        if (lead := _clean_dict(raw_lead, ALL_FIELDS))
    ]
    return {"is_operation": True, "operation": "create", "leads": leads}


def _clean_dict(raw: Any, allowed_fields) -> Dict[str, Any]:
    """Keep only known, truthy fields from an LLM-produced dict."""
    if not isinstance(raw, dict):
        return {}
    return {field: value for field, value in raw.items() if field in allowed_fields and value}


def resolve_missing_name(entities: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    """Given a customer missing a name, use the latest reply to fill it in, mark it as \
    intentionally left blank ("Unknown"), or determine it's still missing. Pure extraction —
    the caller builds any user-facing text itself."""
    model = OllamaQwenModel()
    prompt = NAME_PROMPT.format(known_entities=entities, raw_text=raw_text)
    output_text = model.inference(prompt).strip()

    try:
        parsed = json.loads(_strip_code_fence(output_text))
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    updated = dict(entities)
    for field in OPTIONAL_FIELDS:
        if parsed.get(field):
            updated[field] = parsed[field]

    if parsed.get("name"):
        updated["name"] = parsed["name"]
    elif parsed.get("skip_name"):
        updated["name"] = "Unknown"

    return {"entities": updated, "resolved": bool(updated.get("name"))}


def ask_for_name(entities: Dict[str, Any]) -> str:
    """Deterministic (no LLM call) prompt asking for one specific customer's name, described
    by whatever else is already known about them."""
    bits = []
    if entities.get("tags") and entities.get("property_type"):
        bits.append(f"wants to {entities['tags']} {entities['property_type']}")
    elif entities.get("tags"):
        bits.append(f"wants to {entities['tags']}")
    elif entities.get("property_type"):
        bits.append(f"interested in {entities['property_type']}")
    if entities.get("city"):
        bits.append(f"in {entities['city']}")
    descriptor = f" ({', '.join(bits)})" if bits else ""
    return f"What's the name of the customer{descriptor}?"


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


def _client_for(env: Any) -> "OdooClient | None":
    # Called from inside a running Odoo process (the wizard): use the ORM directly via `env`.
    # Going out over XML-RPC to this same server instead would act in a separate transaction
    # that — under Odoo's REPEATABLE READ isolation — this transaction can't see yet, causing
    # a foreign-key error when e.g. linking a just-created lead back to it. The standalone CLI
    # script has no `env`, so it falls back to a real XML-RPC client.
    return None if env is not None else OdooClient()


def _build_lead_vals(entities: Dict[str, Any], env: Any, client: "OdooClient | None") -> Dict[str, Any]:
    """Build the Odoo vals dict for one customer's entities — shared by create and update so \
    a lead's derived name/description/tags stay consistent between the two."""
    contact_name = entities.get("name") or "Unknown"
    tags = entities.get("tags")
    property_type = entities.get("property_type") or "unspecified"

    description_lines = [f"Operation: {tags or 'unspecified'}", f"Property type: {property_type}"]
    if entities.get("notes"):
        description_lines.append(f"Notes: {entities['notes']}")

    vals = {
        "name": f"{tags or 'unspecified'} - {property_type} - {contact_name}",
        "contact_name": contact_name,
        "email_from": entities.get("email"),
        "phone": entities.get("phone"),
        "description": "\n".join(description_lines),
    }
    # Tag both the operation type and the property type as real crm.tag records (not just
    # text in the name/description) so leads can later be found/deleted/updated by criteria —
    # see find_leads() — instead of an LLM having to guess who matches from conversation history.
    tag_labels = [label for label in (tags, entities.get("property_type")) if label]
    if tag_labels:
        vals["tag_ids"] = [(6, 0, [_resolve_tag_id(env, client, label) for label in tag_labels])]
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
    return vals


def create_lead_from_entities(entities: Dict[str, Any], env: Any = None) -> int:
    """Create a single crm.lead from one customer's entities. Returns the new lead's id."""
    client = _client_for(env)
    vals = _build_lead_vals(entities, env, client)
    if env is not None:
        return env["crm.lead"].create(vals).id
    return client.create_lead(vals)


def describe_lead(entities: Dict[str, Any], lead_id: int) -> str:
    """One confirmation sentence for a single created lead."""
    name = entities.get("name") or "Unknown"
    phone = entities.get("phone")
    tags = entities.get("tags")
    property_type = entities.get("property_type")
    priority_labels = {"0": "low", "1": "medium", "2": "high", "3": "very high"}
    priority = entities.get("priority")
    priority_ref = f", {priority_labels.get(priority, priority)} priority" if priority else ""
    phone_ref = f" ({phone})" if phone else ""

    if tags and property_type:
        article = "an" if property_type[:1].lower() in "aeiou" else "a"
        want_clause = f" who wants to {tags} {article} {property_type}"
    elif tags:
        want_clause = f" who wants to {tags}"
    elif property_type:
        want_clause = f" interested in {property_type}"
    else:
        want_clause = ""

    return f"{name}{phone_ref}{want_clause}{priority_ref} (Odoo lead #{lead_id})"


def describe_filter(criteria: Dict[str, Any]) -> str:
    """Short human-readable label for a delete filter, for the confirmation message."""
    bits = [criteria[field] for field in ("name", "tags", "property_type") if criteria.get(field)]
    return "/".join(bits)


def find_leads(criteria: Dict[str, Any], env: Any = None) -> List[tuple]:
    """Look up existing crm.lead records matching all of the given criteria — a customer \
    name (substring match) and/or tag labels (operation type, property type, matched against \
    the real tag_ids set at creation time, not guessed from conversation history). Returns \
    [(id, display_name), ...]. Requires at least one criterion, or nothing is returned."""
    domain = []
    if criteria.get("name"):
        domain.append(("contact_name", "ilike", criteria["name"].strip()))
    for field in ("tags", "property_type"):
        if criteria.get(field):
            domain.append(("tag_ids.name", "ilike", criteria[field].strip()))
    if not domain:
        return []

    if env is not None:
        leads = env["crm.lead"].search(domain)
        return [(lead.id, lead.contact_name or lead.name) for lead in leads]
    records = OdooClient().search_read("crm.lead", domain, ["contact_name", "name"])
    return [(record["id"], record.get("contact_name") or record["name"]) for record in records]


def delete_leads(lead_ids: List[int], env: Any = None) -> None:
    """Delete the given crm.lead records."""
    if env is not None:
        env["crm.lead"].browse(lead_ids).unlink()
    else:
        OdooClient().unlink("crm.lead", lead_ids)


def _read_lead_entities(lead_id: int, env: Any, client: "OdooClient | None") -> Dict[str, Any]:
    """Read an existing crm.lead back into our entities dict shape, so it can be merged with \
    requested updates and rebuilt via _build_lead_vals for full consistency."""
    if env is not None:
        lead = env["crm.lead"].browse(lead_id)
        entities = {
            "name": lead.contact_name,
            "email": lead.email_from,
            "phone": lead.phone,
            "priority": lead.priority,
            "company_name": lead.partner_name,
            "street": lead.street,
            "street2": lead.street2,
            "city": lead.city,
            "country": lead.country_id.name if lead.country_id else None,
            "website": lead.website,
        }
        tag_names = {tag.name.lower() for tag in lead.tag_ids}
    else:
        fields = [
            "contact_name", "email_from", "phone", "priority", "partner_name",
            "street", "street2", "city", "country_id", "website", "tag_ids",
        ]
        records = client.search_read("crm.lead", [("id", "=", lead_id)], fields)
        record = records[0] if records else {}
        country = record.get("country_id")
        entities = {
            "name": record.get("contact_name"),
            "email": record.get("email_from"),
            "phone": record.get("phone"),
            "priority": record.get("priority"),
            "company_name": record.get("partner_name"),
            "street": record.get("street"),
            "street2": record.get("street2"),
            "city": record.get("city"),
            "country": country[1] if country else None,
            "website": record.get("website"),
        }
        tag_ids = record.get("tag_ids") or []
        tag_names = set()
        if tag_ids:
            tags = client.search_read("crm.tag", [("id", "in", tag_ids)], ["name"])
            tag_names = {tag["name"].lower() for tag in tags}

    for label in tag_names:
        if label in OPERATION_TAGS:
            entities["tags"] = label
        elif label in PROPERTY_TAGS:
            entities["property_type"] = label

    return {field: value for field, value in entities.items() if value}


def update_leads(criteria: Dict[str, Any], updates: Dict[str, Any], env: Any = None) -> List[tuple]:
    """Find leads matching criteria and apply the given field updates to each, reusing \
    _build_lead_vals so the derived name/description/tags stay consistent — e.g. changing \
    "tags" from sell to buy correctly swaps the crm.tag too, not just the description text. \
    Returns [(id, display_name), ...] for whatever was updated."""
    matches = find_leads(criteria, env=env)
    if not matches:
        return []

    client = _client_for(env)
    updated = []
    for lead_id, _ in matches:
        current = _read_lead_entities(lead_id, env, client)
        merged = {**current, **updates}
        vals = _build_lead_vals(merged, env, client)
        if env is not None:
            env["crm.lead"].browse(lead_id).write(vals)
        else:
            client.write("crm.lead", [lead_id], vals)
        updated.append((lead_id, merged.get("name") or "Unknown"))

    return updated


def describe_update(criteria: Dict[str, Any], updates: Dict[str, Any]) -> str:
    """Short human-readable label for an update request, for the confirmation message."""
    changes = ", ".join(f"{field}={value}" for field, value in updates.items())
    return f"{describe_filter(criteria)} -> {changes}"
