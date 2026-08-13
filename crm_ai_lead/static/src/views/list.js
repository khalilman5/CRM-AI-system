/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";

export class CrmAiLeadListController extends ListController {
    static template = "crm_ai_lead.ListView";

    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async onNewLeadAI() {
        await this.actionService.doAction("crm_ai_lead.crm_ai_lead_wizard_action");
    }
}

registry.category("views").add("crm_ai_lead_list", {
    ...listView,
    Controller: CrmAiLeadListController,
});
