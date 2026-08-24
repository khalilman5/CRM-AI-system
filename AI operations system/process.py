"""Standalone terminal chat client for exercising nodes.py without Odoo's web UI.

Mirrors crm_ai_lead_wizard.py's orchestration exactly (same functions, same
queue-based clarification for customers missing a name, same create/delete/
update dispatch), so this is a quick way to test prompt/behavior changes
from a terminal. Creates/deletes/updates real leads over XML-RPC via
odoo_client.py, so ODOO_URL/DB/USERNAME/PASSWORD must be set.
"""

import nodes


def continue_pending_create(pending_queue, text):
    result = nodes.resolve_missing_name(pending_queue[0], text)
    created_summaries = []
    if result["resolved"]:
        lead_id = nodes.create_lead_from_entities(result["entities"])
        created_summaries.append(nodes.describe_lead(result["entities"], lead_id))
        pending_queue = pending_queue[1:]
    else:
        pending_queue = [result["entities"]] + pending_queue[1:]
    return finish_create(created_summaries, pending_queue), pending_queue


def handle_create(leads):
    created_summaries = []
    pending_queue = []
    for lead_entities in leads:
        if lead_entities.get("name"):
            lead_id = nodes.create_lead_from_entities(lead_entities)
            created_summaries.append(nodes.describe_lead(lead_entities, lead_id))
        else:
            pending_queue.append(lead_entities)
    return finish_create(created_summaries, pending_queue), pending_queue


def finish_create(created_summaries, pending_queue):
    reply_parts = []
    if created_summaries:
        plural = "s" if len(created_summaries) > 1 else ""
        reply_parts.append(f"Created lead{plural} for: {'; '.join(created_summaries)}.")
    if pending_queue:
        reply_parts.append(nodes.ask_for_name(pending_queue[0]))
    return " ".join(reply_parts) or "Got it."


def handle_delete(delete_filters):
    if not delete_filters:
        return "I couldn't tell what to delete — a customer's name, or an operation/property type to match on?"

    summaries = []
    for criteria in delete_filters:
        label = nodes.describe_filter(criteria)
        matches = nodes.find_leads(criteria)
        if not matches:
            summaries.append(f'No lead found matching "{label}".')
            continue
        nodes.delete_leads([lead_id for lead_id, _ in matches])
        names = ", ".join(f"#{lead_id} ({name})" for lead_id, name in matches)
        plural = "s" if len(matches) > 1 else ""
        summaries.append(f'Deleted {len(matches)} lead{plural} matching "{label}": {names}.')
    return " ".join(summaries)


def handle_update(update_filters):
    if not update_filters:
        return "I couldn't tell what to update — which customer(s), and what should change?"

    summaries = []
    for entry in update_filters:
        criteria, updates = entry["criteria"], entry["updates"]
        label = nodes.describe_update(criteria, updates)
        matches = nodes.update_leads(criteria, updates)
        if not matches:
            summaries.append(f'No lead found matching "{nodes.describe_filter(criteria)}".')
            continue
        names = ", ".join(f"#{lead_id} ({name})" for lead_id, name in matches)
        plural = "s" if len(matches) > 1 else ""
        summaries.append(f"Updated {len(matches)} lead{plural} ({label}): {names}.")
    return " ".join(summaries)


def main():
    history = []
    pending_queue = []

    print("Type a message (Ctrl+C to quit).")
    while True:
        text = input("You: ").strip()
        if not text:
            continue

        history.append({"role": "user", "content": text})

        if pending_queue:
            reply, pending_queue = continue_pending_create(pending_queue, text)
        else:
            state = {"raw_text": text, "history": history}
            state.update(nodes.verify_operation(state))
            if not state.get("is_operation"):
                reply = state.get("final_message")
            elif state.get("operation") == "delete":
                reply = handle_delete(state.get("delete_filters", []))
            elif state.get("operation") == "update":
                reply = handle_update(state.get("update_filters", []))
            else:
                reply, pending_queue = handle_create(state.get("leads", []))

        print(f"Assistant: {reply}\n")
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
