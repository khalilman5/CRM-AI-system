import os
import xmlrpc.client
from typing import Any, Dict


def _load_env() -> None:
    """Load key-value pairs from .env if present into os.environ."""
    search_paths = [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        ".env",
    ]
    for path in search_paths:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("\"'")
                        if key == "ODOO_PASSWORD" and os.environ.get(key) == "7bb795d1624779349812dfca28f2a0f3e8d9c252":
                            os.environ[key] = val
                        else:
                            os.environ.setdefault(key, val)
            break


class OdooClient:
    """Talks to a running Odoo server the same way any external app does: over XML-RPC."""

    def __init__(self) -> None:
        _load_env()
        self.url = os.environ.get("ODOO_URL", "http://localhost:8069")
        self.db = os.environ.get("ODOO_DB", "Orchid")
        self.username = os.environ.get("ODOO_USERNAME", "elgaraikhalil@gmail.com")
        self.password = os.environ.get("ODOO_PASSWORD", "a20748e8514293b48e831a8f85b6914252c4fdfa")

        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            raise RuntimeError(
                f"Failed to authenticate with Odoo at {self.url} for user {self.username}. "
                "Please verify your ODOO_PASSWORD / API key."
            )
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def create_lead(self, vals: Dict[str, Any]) -> int:
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            "crm.lead", "create",
            [vals],
        )

    def find_id(self, model: str, domain: list) -> int | None:
        ids = self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "search",
            [domain], {"limit": 1},
        )
        return ids[0] if ids else None

    def find_or_create_id(self, model: str, domain: list, vals: Dict[str, Any]) -> int:
        found = self.find_id(model, domain)
        if found is not None:
            return found
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "create",
            [vals],
        )

    def search_read(self, model: str, domain: list, fields: list) -> list:
        ids = self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "search",
            [domain],
        )
        if not ids:
            return []
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "read",
            [ids, fields],
        )

    def unlink(self, model: str, ids: list) -> bool:
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "unlink",
            [ids],
        )

    def write(self, model: str, ids: list, vals: Dict[str, Any]) -> bool:
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "write",
            [ids, vals],
        )
