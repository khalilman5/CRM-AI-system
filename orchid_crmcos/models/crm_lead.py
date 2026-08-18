import re

from odoo import fields, models
from odoo.tools import html2plaintext


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # =========================================================
    # Custom Orchid Island fields
    # =========================================================

    x_client_email = fields.Char(
        string="Client Email"
    )

    x_property_type = fields.Char(
        string="Property Type"
    )

    x_contact_subject = fields.Char(
        string="Contact Subject"
    )

    x_ai_score = fields.Integer(
        string="AI Lead Score"
    )

    x_ai_priority = fields.Selection(
        [
            ("cold", "Cold"),
            ("warm", "Warm"),
            ("hot", "Hot"),
            ("very_hot", "Very Hot"),
        ],
        string="AI Priority",
    )

    x_ai_intent = fields.Char(
        string="Client Intent"
    )

    x_ai_budget = fields.Float(
        string="Budget"
    )

    x_ai_currency = fields.Char(
        string="Currency"
    )

    x_ai_location = fields.Char(
        string="Preferred Location"
    )

    x_ai_timeline = fields.Char(
        string="Timeline"
    )

    x_ai_summary = fields.Text(
        string="AI Summary"
    )

    # =========================================================
    # Helper: extract KEY: VALUE from incoming email
    # =========================================================

    def _extract_email_value(self, text, key):
        """
        Extracts values from structured email lines.

        Example:
        FULL_NAME: Sara Martin
        AI_SCORE: 84
        """

        pattern = rf"{re.escape(key)}\s*:\s*([^\r\n]+)"

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return match.group(1).strip()

        return False

    # =========================================================
    # Incoming email → CRM Lead
    # =========================================================

    def message_new(self, msg_dict, custom_values=None):
        """
        Called when Odoo receives an email that creates
        a new CRM lead.

        Website email
            ↓
        Odoo mail processing
            ↓
        crm.lead.message_new()
            ↓
        This method extracts form + AI information
            ↓
        New CRM lead
        """

        values = dict(custom_values or {})

        # -----------------------------------------------------
        # Email body
        # -----------------------------------------------------

        html_body = msg_dict.get("body", "") or ""

        text = html2plaintext(
            str(html_body)
        )

        # =====================================================
        # 1. ORIGINAL WEBSITE FORM DATA
        # =====================================================

        full_name = self._extract_email_value(
            text,
            "FULL_NAME",
        )

        client_email = self._extract_email_value(
            text,
            "EMAIL",
        )

        phone = self._extract_email_value(
            text,
            "PHONE",
        )

        property_type = self._extract_email_value(
            text,
            "PROPERTY_TYPE",
        )

        contact_subject = self._extract_email_value(
            text,
            "SUBJECT",
        )

        client_message = self._extract_email_value(
            text,
            "MESSAGE",
        )

        # =====================================================
        # 2. AI DATA
        # =====================================================

        score = self._extract_email_value(
            text,
            "AI_SCORE",
        )

        priority = self._extract_email_value(
            text,
            "AI_PRIORITY",
        )

        intent = self._extract_email_value(
            text,
            "AI_INTENT",
        )

        budget = self._extract_email_value(
            text,
            "AI_BUDGET",
        )

        currency = self._extract_email_value(
            text,
            "AI_CURRENCY",
        )

        location = self._extract_email_value(
            text,
            "AI_LOCATION",
        )

        timeline = self._extract_email_value(
            text,
            "AI_TIMELINE",
        )

        summary = self._extract_email_value(
            text,
            "AI_SUMMARY",
        )

        # =====================================================
        # 3. STANDARD ODOO CRM FIELDS
        # =====================================================

        if full_name:
            values["contact_name"] = full_name

        if phone:
            values["phone"] = phone

        if client_message:
            values["description"] = client_message

        # =====================================================
        # 4. ORCHID WEBSITE FIELDS
        # =====================================================

        if client_email:
            values["x_client_email"] = client_email

        if property_type:
            values["x_property_type"] = property_type

        if contact_subject:
            values["x_contact_subject"] = contact_subject

        # =====================================================
        # 5. AI SCORE
        # =====================================================

        if score:
            try:
                parsed_score = int(score)

                values["x_ai_score"] = max(
                    0,
                    min(100, parsed_score),
                )

            except (ValueError, TypeError):
                pass

        # =====================================================
        # 6. AI PRIORITY
        # =====================================================

        if priority:

            normalized_priority = (
                priority
                .strip()
                .lower()
                .replace(" ", "_")
            )

            allowed_priorities = {
                "cold",
                "warm",
                "hot",
                "very_hot",
            }

            if normalized_priority in allowed_priorities:
                values["x_ai_priority"] = normalized_priority

        # =====================================================
        # 7. OTHER AI DATA
        # =====================================================

        if intent:
            values["x_ai_intent"] = intent

        if budget:
            try:
                values["x_ai_budget"] = float(budget)

            except (ValueError, TypeError):
                pass

        if currency:
            values["x_ai_currency"] = currency

        if location:
            values["x_ai_location"] = location

        if timeline:
            values["x_ai_timeline"] = timeline

        if summary:
            values["x_ai_summary"] = summary

        # =====================================================
        # 8. CREATE NORMAL ODOO CRM RECORD
        # =====================================================

        return super().message_new(
            msg_dict,
            custom_values=values,
        )