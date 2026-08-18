import json
import os
import sys

from odoo import api, fields, models

# The LangGraph pipeline lives in a separate, non-addon folder (its name has
# a space, so it can't be imported as a normal Python package). Add it to
# sys.path so we can import it directly.
_AI_OPS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'AI operations system')
)
if _AI_OPS_DIR not in sys.path:
    sys.path.insert(0, _AI_OPS_DIR)


class CrmAiLeadWizard(models.TransientModel):
    _name = 'crm.ai.lead.wizard'
    _description = 'New Lead AI Chat'

    message_ids = fields.One2many('crm.ai.lead.wizard.message', 'wizard_id', string='Conversation')
    # Short-term memory: the entities/missing_fields/intent gathered so far,
    # kept between replies until the lead is created.
    state_json = fields.Text(string='Conversation State')
    # A throwaway wizard record shouldn't be able to block deleting the real
    # lead it once pointed to.
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

        if not prior:
            state = {'raw_text': text, 'history': history, 'env': self.env}
            state.update(nodes.verify_operation(state))
            if not state.get('is_operation'):
                self.env['crm.ai.lead.wizard.message'].create({
                    'wizard_id': self.id,
                    'role': 'assistant',
                    'content': state.get('final_message'),
                })
                return

            state.update(nodes.validate(state))
            if not state.get('is_valid'):
                state.update(nodes.ask_clarification(state))
        else:
            state = {
                'raw_text': text,
                'history': history,
                'env': self.env,
                'intent': prior.get('intent'),
                'entities': prior.get('entities', {}),
                'missing_fields': prior.get('missing_fields', []),
            }
            state.update(nodes.ask_clarification(state))

        if state.get('is_valid'):
            state.update(nodes.execute_action(state))
            state.update(nodes.respond(state))
            reply = state.get('final_message')
            lead_id = state.get('tool_result', {}).get('lead_id')
            self.state_json = False
            if lead_id:
                self.lead_id = lead_id
        else:
            reply = state.get('clarification_prompt') or 'I need a bit more information before creating the lead.'
            self.state_json = json.dumps({
                'intent': state.get('intent'),
                'entities': state.get('entities', {}),
                'missing_fields': state.get('missing_fields', []),
            })

        self.env['crm.ai.lead.wizard.message'].create({
            'wizard_id': self.id,
            'role': 'assistant',
            'content': reply,
        })


class CrmAiLeadWizardMessage(models.TransientModel):
    _name = 'crm.ai.lead.wizard.message'
    _description = 'New Lead AI Chat Message'
    _order = 'id asc'

    wizard_id = fields.Many2one('crm.ai.lead.wizard', required=True, ondelete='cascade')
    role = fields.Selection([('user', 'User'), ('assistant', 'Assistant')], required=True)
    content = fields.Text(required=True)
