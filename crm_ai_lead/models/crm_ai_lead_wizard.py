import os
import sys

from odoo import fields, models
from odoo.exceptions import UserError

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
    _description = 'New Lead AI Prompt'

    prompt = fields.Text(string='Prompt', required=True)

    def action_generate_lead(self):
        self.ensure_one()
        import process as ai_process

        result = ai_process.app.invoke({'raw_text': self.prompt})
        lead_id = result.get('tool_result', {}).get('lead_id')

        if lead_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'crm.lead',
                'res_id': lead_id,
                'view_mode': 'form',
                'target': 'current',
            }

        raise UserError(result.get('final_message') or 'Could not create the lead.')
