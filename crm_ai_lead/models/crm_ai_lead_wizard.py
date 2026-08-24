import json
import os
import sys

from odoo import api, fields, models

# nodes.py lives in a separate, non-addon folder (its name has a space, so
# it can't be imported as a normal Python package). Add it to sys.path so we
# can import it directly.
_AI_OPS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'AI operations system')
)
if _AI_OPS_DIR not in sys.path:
    sys.path.insert(0, _AI_OPS_DIR)


class CrmAiLeadWizard(models.TransientModel):
    _name = 'crm.ai.lead.wizard'
    _description = 'New Lead AI Chat'

    message_ids = fields.One2many('crm.ai.lead.wizard.message', 'wizard_id', string='Conversation')
    # Short-term memory: customers already parsed out of the conversation that
    # are still missing a name, queued up one at a time until each is resolved.
    state_json = fields.Text(string='Conversation State')
    # A throwaway wizard record shouldn't be able to block deleting the real
    # lead it once pointed to. Only ever holds the most recently created lead
    # (a single message can now create several) — informational only.
    lead_id = fields.Many2one('crm.lead', string='Created Lead', readonly=True, ondelete='set null')

    @api.model
    def default_get(self, fields_list):
        # This wizard is meant to be throwaway: wipe any of this user's earlier
        # conversations so opening "New Lead AI" always starts from a blank chat,
        # instead of waiting on Odoo's hourly transient-record cleanup.
        self.sudo().search([('create_uid', '=', self.env.uid)]).unlink()
        return super().default_get(fields_list)

    def action_send_message(self, message):
        self.ensure_one()
        text = (message or '').strip()
        if not text:
            return

        history = [{'role': m.role, 'content': m.content} for m in self.message_ids]

        self.env['crm.ai.lead.wizard.message'].create({
            'wizard_id': self.id,
            'role': 'user',
            'content': text,
        })

        import nodes

        prior = json.loads(self.state_json) if self.state_json else {}
        pending_queue = prior.get('pending_queue', [])

        if pending_queue:
            # This message is the answer to "what's this customer's name?" —
            # resolve the one we're currently waiting on.
            reply = self._continue_pending_create(nodes, pending_queue, text)
        else:
            state = {'raw_text': text, 'history': history}
            state.update(nodes.verify_operation(state))
            if not state.get('is_operation'):
                reply = state.get('final_message')
            elif state.get('operation') == 'delete':
                reply = self._handle_delete(nodes, state.get('delete_filters', []))
            elif state.get('operation') == 'update':
                reply = self._handle_update(nodes, state.get('update_filters', []))
            else:
                reply = self._handle_create(nodes, state.get('leads', []))

        self.env['crm.ai.lead.wizard.message'].create({
            'wizard_id': self.id,
            'role': 'assistant',
            'content': reply,
        })

    def _continue_pending_create(self, nodes, pending_queue, text):
        result = nodes.resolve_missing_name(pending_queue[0], text)
        created_summaries = []
        if result['resolved']:
            lead_id = nodes.create_lead_from_entities(result['entities'], env=self.env)
            created_summaries.append(nodes.describe_lead(result['entities'], lead_id))
            self.lead_id = lead_id
            pending_queue = pending_queue[1:]
        else:
            pending_queue = [result['entities']] + pending_queue[1:]
        return self._finish_create(nodes, created_summaries, pending_queue)

    def _handle_create(self, nodes, leads):
        created_summaries = []
        pending_queue = []
        for lead_entities in leads:
            if lead_entities.get('name'):
                lead_id = nodes.create_lead_from_entities(lead_entities, env=self.env)
                created_summaries.append(nodes.describe_lead(lead_entities, lead_id))
                self.lead_id = lead_id
            else:
                pending_queue.append(lead_entities)
        return self._finish_create(nodes, created_summaries, pending_queue)

    def _finish_create(self, nodes, created_summaries, pending_queue):
        reply_parts = []
        if created_summaries:
            plural = 's' if len(created_summaries) > 1 else ''
            reply_parts.append(f"Created lead{plural} for: {'; '.join(created_summaries)}.")
        if pending_queue:
            reply_parts.append(nodes.ask_for_name(pending_queue[0]))
            self.state_json = json.dumps({'pending_queue': pending_queue})
        else:
            self.state_json = False
        return ' '.join(reply_parts) or 'Got it.'

    def _handle_delete(self, nodes, delete_filters):
        if not delete_filters:
            return "I couldn't tell what to delete — a customer's name, or an operation/property type to match on?"

        summaries = []
        for criteria in delete_filters:
            label = nodes.describe_filter(criteria)
            matches = nodes.find_leads(criteria, env=self.env)
            if not matches:
                summaries.append(f'No lead found matching "{label}".')
                continue
            nodes.delete_leads([lead_id for lead_id, _ in matches], env=self.env)
            names = ', '.join(f'#{lead_id} ({name})' for lead_id, name in matches)
            plural = 's' if len(matches) > 1 else ''
            summaries.append(f'Deleted {len(matches)} lead{plural} matching "{label}": {names}.')

        self.state_json = False
        return ' '.join(summaries)

    def _handle_update(self, nodes, update_filters):
        if not update_filters:
            return "I couldn't tell what to update — which customer(s), and what should change?"

        summaries = []
        for entry in update_filters:
            criteria, updates = entry['criteria'], entry['updates']
            label = nodes.describe_update(criteria, updates)
            matches = nodes.update_leads(criteria, updates, env=self.env)
            if not matches:
                summaries.append(f'No lead found matching "{nodes.describe_filter(criteria)}".')
                continue
            names = ', '.join(f'#{lead_id} ({name})' for lead_id, name in matches)
            plural = 's' if len(matches) > 1 else ''
            summaries.append(f'Updated {len(matches)} lead{plural} ({label}): {names}.')

        self.state_json = False
        return ' '.join(summaries)


class CrmAiLeadWizardMessage(models.TransientModel):
    _name = 'crm.ai.lead.wizard.message'
    _description = 'New Lead AI Chat Message'
    _order = 'id asc'

    wizard_id = fields.Many2one('crm.ai.lead.wizard', required=True, ondelete='cascade')
    role = fields.Selection([('user', 'User'), ('assistant', 'Assistant')], required=True)
    content = fields.Text(required=True)
