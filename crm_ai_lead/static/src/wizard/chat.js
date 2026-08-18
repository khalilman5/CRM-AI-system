/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onPatched, useRef, useState } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class CrmAiLeadChat extends Component {
    static template = "crm_ai_lead.ChatMessages";
    static props = { ...standardFieldProps };

    setup() {
        this.rootRef = useRef("chatRoot");
        this.orm = useService("orm");
        this.state = useState({
            text: "",
            pendingUser: null,
            isWaiting: false,
        });
        onMounted(() => this.scrollToBottom());
        onPatched(() => this.scrollToBottom());
    }

    scrollToBottom() {
        if (this.rootRef.el) {
            this.rootRef.el.scrollTop = this.rootRef.el.scrollHeight;
        }
    }

    get messages() {
        const list = this.props.record.data[this.props.name];
        return list ? list.records.map((r) => r.data) : [];
    }

    get canSend() {
        return Boolean(this.state.text.trim()) && !this.state.isWaiting;
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    // Show the user's own message and a typing indicator right away instead
    // of waiting for the LLM round-trip (which can take several seconds) to
    // show anything at all.
    async send() {
        const text = this.state.text.trim();
        if (!text || this.state.isWaiting) {
            return;
        }
        this.state.text = "";
        this.state.pendingUser = text;
        this.state.isWaiting = true;
        try {
            if (!this.props.record.resId) {
                await this.props.record.save();
            }
            await this.orm.call(this.props.record.resModel, "action_send_message", [
                [this.props.record.resId],
                text,
            ]);
            await this.props.record.load();
        } finally {
            this.state.pendingUser = null;
            this.state.isWaiting = false;
        }
    }
}

registry.category("fields").add("crm_ai_lead_chat", {
    component: CrmAiLeadChat,
    supportedTypes: ["one2many"],
    // Without an inline <list> sub-view, Odoo doesn't know which fields of
    // the related records to fetch — declare them explicitly, or role/content
    // are never loaded and no bubble ever has anything to show.
    relatedFields: [
        { name: "role", type: "selection" },
        { name: "content", type: "text" },
    ],
});
