import os
import xmlrpc.client
from typing import Any, Dict


class OdooClient:
    """Talks to a running Odoo server the same way any external app does: over XML-RPC."""

    def __init__(self) -> None:
        self.url = os.environ["ODOO_URL"]
        self.db = os.environ["ODOO_DB"]
        self.username = os.environ["ODOO_USERNAME"]
        self.password = os.environ["ODOO_PASSWORD"]

        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(self.db, self.username, self.password, {})
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def create_lead(self, vals: Dict[str, Any]) -> int:
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            "crm.lead", "create",
            [vals],
        )
