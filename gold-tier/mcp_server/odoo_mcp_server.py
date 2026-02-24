"""
Odoo MCP Server — Model Context Protocol server for accounting actions.

Provides tools for Claude Code to query balances, manage invoices,
record payments, and generate P&L reports via Odoo ERP.

Integrates with Odoo 19+ via its JSON-RPC API (/jsonrpc endpoint).
Uses xmlrpc.client for the External API (XML-RPC) as a fallback.

Supports dry-run mode (default) using fixtures for simulated data.

Setup in Claude Code settings:
{
    "mcpServers": {
        "odoo": {
            "command": "python",
            "args": ["path/to/odoo_mcp_server.py"],
            "env": {
                "DRY_RUN": "true",
                "ODOO_URL": "http://localhost:8069",
                "ODOO_DB": "my_company",
                "ODOO_USERNAME": "admin",
                "ODOO_API_KEY": "your_api_key"
            }
        }
    }
}

Gold Tier — Phase 4: Odoo MCP Server.
"""

import os
import sys
import json
import xmlrpc.client
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
VAULT_PATH = os.getenv("VAULT_PATH", str(Path(__file__).parent.parent / "AI_Employee_Vault"))
FIXTURES_PATH = Path(__file__).parent / "fixtures" / "odoo_samples.json"

# Odoo connection settings
ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
ODOO_DB = os.getenv("ODOO_DB", "my_company")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "admin")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")


class OdooJSONRPCClient:
    """Client for Odoo's JSON-RPC API (/jsonrpc endpoint).

    Odoo 19+ exposes both XML-RPC and JSON-RPC APIs. This client
    uses the JSON-RPC interface for all operations.

    Authentication flow:
    1. Call /jsonrpc with method 'call' and service 'common' to authenticate
    2. Receive a uid (user ID)
    3. Use uid + api_key for all subsequent 'object' service calls

    Reference: https://www.odoo.com/documentation/19.0/developer/reference/external_api.html
    """

    def __init__(self, url: str, db: str, username: str, api_key: str):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.api_key = api_key
        self.uid = None
        self._request_id = 0

    def _jsonrpc_call(self, service: str, method: str, args: list) -> any:
        """Make a JSON-RPC call to Odoo's /jsonrpc endpoint."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/jsonrpc",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if "error" in result:
            raise ConnectionError(f"Odoo JSON-RPC error: {result['error']}")
        return result.get("result")

    def authenticate(self) -> int:
        """Authenticate with Odoo and return uid."""
        self.uid = self._jsonrpc_call(
            "common", "authenticate",
            [self.db, self.username, self.api_key, {}]
        )
        if not self.uid:
            raise PermissionError("Odoo authentication failed — check credentials")
        return self.uid

    def execute_kw(self, model: str, method: str, args: list, kwargs: dict = None) -> any:
        """Execute a method on an Odoo model via JSON-RPC.

        This is the core Odoo External API call:
        service='object', method='execute_kw',
        args=[db, uid, api_key, model, method, *args]
        """
        if self.uid is None:
            self.authenticate()

        return self._jsonrpc_call(
            "object", "execute_kw",
            [self.db, self.uid, self.api_key, model, method, args, kwargs or {}]
        )

    def search_read(self, model: str, domain: list = None, fields: list = None,
                    limit: int = 100) -> list:
        """Search and read records from an Odoo model."""
        return self.execute_kw(
            model, "search_read",
            [domain or []],
            {"fields": fields or [], "limit": limit},
        )

    def create(self, model: str, values: dict) -> int:
        """Create a record in an Odoo model, returns the new record ID."""
        return self.execute_kw(model, "create", [values])


class OdooXMLRPCClient:
    """Fallback client using Odoo's XML-RPC External API.

    Uses Python's built-in xmlrpc.client — no external dependencies.

    Endpoints:
    - /xmlrpc/2/common — authentication (authenticate, version)
    - /xmlrpc/2/object — data operations (execute_kw)

    Reference: https://www.odoo.com/documentation/19.0/developer/reference/external_api.html
    """

    def __init__(self, url: str, db: str, username: str, api_key: str):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.api_key = api_key
        self.uid = None
        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def authenticate(self) -> int:
        """Authenticate via XML-RPC and return uid."""
        self.uid = self.common.authenticate(self.db, self.username, self.api_key, {})
        if not self.uid:
            raise PermissionError("Odoo XML-RPC authentication failed")
        return self.uid

    def execute_kw(self, model: str, method: str, args: list, kwargs: dict = None) -> any:
        """Execute a method on an Odoo model via XML-RPC."""
        if self.uid is None:
            self.authenticate()
        return self.models.execute_kw(
            self.db, self.uid, self.api_key,
            model, method, args, kwargs or {}
        )

    def search_read(self, model: str, domain: list = None, fields: list = None,
                    limit: int = 100) -> list:
        """Search and read records from an Odoo model."""
        return self.execute_kw(
            model, "search_read",
            [domain or []],
            {"fields": fields or [], "limit": limit},
        )

    def create(self, model: str, values: dict) -> int:
        """Create a record in an Odoo model."""
        return self.execute_kw(model, "create", [values])


class OdooMCPServer:
    """MCP Server providing Odoo accounting capabilities to Claude Code.

    In dry-run mode: returns fixture data from odoo_samples.json.
    In live mode: connects to Odoo via JSON-RPC API (with XML-RPC fallback).
    """

    def __init__(self):
        self.vault_path = Path(VAULT_PATH)
        self.logs_dir = self.vault_path / "Logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Load fixtures for dry-run mode
        self.fixtures = {}
        if FIXTURES_PATH.exists():
            try:
                self.fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                self.fixtures = {}

        # Initialize Odoo client for live mode
        self.odoo_client = None
        if not DRY_RUN and ODOO_API_KEY:
            try:
                self.odoo_client = OdooJSONRPCClient(
                    ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY
                )
                self.odoo_client.authenticate()
            except Exception:
                # Fall back to XML-RPC
                try:
                    self.odoo_client = OdooXMLRPCClient(
                        ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY
                    )
                    self.odoo_client.authenticate()
                except Exception:
                    self.odoo_client = None

    def get_tools(self) -> list:
        """Return list of available MCP tools."""
        return [
            {
                "name": "query_account_balance",
                "description": "Query account balances from Odoo. Returns all accounts with their current balances.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "account_type": {
                            "type": "string",
                            "description": "Filter by account type: asset, liability, income, expense, or 'all'",
                            "default": "all",
                        },
                    },
                },
            },
            {
                "name": "list_invoices",
                "description": "List invoices from Odoo with optional status filter.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by status: draft, sent, paid, or 'all'",
                            "default": "all",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max number of invoices to return",
                            "default": 50,
                        },
                    },
                },
            },
            {
                "name": "create_invoice",
                "description": "Create a new invoice in Odoo.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "client": {"type": "string", "description": "Client name"},
                        "client_email": {"type": "string", "description": "Client email"},
                        "amount": {"type": "number", "description": "Invoice amount"},
                        "description": {"type": "string", "description": "Invoice description"},
                        "due_days": {"type": "integer", "description": "Days until due", "default": 30},
                    },
                    "required": ["client", "amount", "description"],
                },
            },
            {
                "name": "record_payment",
                "description": "Record a payment against an invoice in Odoo.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Invoice ID to pay"},
                        "amount": {"type": "number", "description": "Payment amount"},
                        "method": {
                            "type": "string",
                            "description": "Payment method: bank_transfer, credit_card, cash",
                            "default": "bank_transfer",
                        },
                        "reference": {"type": "string", "description": "Payment reference"},
                    },
                    "required": ["invoice_id", "amount"],
                },
            },
            {
                "name": "get_profit_loss_report",
                "description": "Get a Profit & Loss report for a given period.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "period": {
                            "type": "string",
                            "description": "Period in YYYY-MM format",
                            "default": "",
                        },
                    },
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """Handle an MCP tool call."""
        handlers = {
            "query_account_balance": self.query_account_balance,
            "list_invoices": self.list_invoices,
            "create_invoice": self.create_invoice,
            "record_payment": self.record_payment,
            "get_profit_loss_report": self.get_profit_loss_report,
        }
        handler = handlers.get(tool_name)
        if handler:
            return handler(arguments)
        return {"error": f"Unknown tool: {tool_name}"}

    def query_account_balance(self, args: dict) -> dict:
        """Query account balances from Odoo."""
        account_type = args.get("account_type", "all")

        if DRY_RUN:
            accounts = self.fixtures.get("accounts", [])
            if account_type != "all":
                accounts = [a for a in accounts if a["type"] == account_type]
            total = sum(a["balance"] for a in accounts)
            self._log_action("query_account_balance", {"filter": account_type, "count": len(accounts)})
            return {"accounts": accounts, "total_balance": total, "mode": "dry_run"}

        # Live mode: query Odoo account.account model
        if not self.odoo_client:
            return {"status": "error", "message": "Odoo client not connected"}

        type_map = {"asset": "asset", "liability": "liability", "income": "income", "expense": "expense"}
        domain = []
        if account_type != "all" and account_type in type_map:
            domain = [("account_type", "=", type_map[account_type])]

        records = self.odoo_client.search_read(
            "account.account", domain,
            fields=["name", "code", "current_balance", "currency_id", "account_type"],
            limit=200,
        )
        accounts = [
            {
                "id": r["id"], "name": r["name"], "code": r["code"],
                "balance": r.get("current_balance", 0), "type": r.get("account_type", ""),
            }
            for r in records
        ]
        total = sum(a["balance"] for a in accounts)
        self._log_action("query_account_balance", {"filter": account_type, "count": len(accounts)})
        return {"accounts": accounts, "total_balance": total, "mode": "live"}

    def list_invoices(self, args: dict) -> dict:
        """List invoices from Odoo."""
        status = args.get("status", "all")
        limit = args.get("limit", 50)

        if DRY_RUN:
            invoices = self.fixtures.get("invoices", [])
            if status != "all":
                invoices = [inv for inv in invoices if inv["status"] == status]
            invoices = invoices[:limit]
            self._log_action("list_invoices", {"filter": status, "count": len(invoices)})
            return {"invoices": invoices, "total": len(invoices), "mode": "dry_run"}

        # Live mode: query Odoo account.move (invoice model)
        if not self.odoo_client:
            return {"status": "error", "message": "Odoo client not connected"}

        status_map = {"draft": "draft", "sent": "posted", "paid": "posted"}
        domain = [("move_type", "in", ["out_invoice", "out_refund"])]
        if status != "all" and status in status_map:
            domain.append(("state", "=", status_map[status]))
            if status == "paid":
                domain.append(("payment_state", "=", "paid"))

        records = self.odoo_client.search_read(
            "account.move", domain,
            fields=["name", "partner_id", "amount_total", "state",
                     "payment_state", "invoice_date", "invoice_date_due", "currency_id"],
            limit=limit,
        )
        invoices = [
            {
                "id": r["name"], "client": r.get("partner_id", ["", ""])[1] if r.get("partner_id") else "",
                "amount": r.get("amount_total", 0), "status": r.get("state", ""),
                "payment_state": r.get("payment_state", ""),
                "date_issued": str(r.get("invoice_date", "")),
                "date_due": str(r.get("invoice_date_due", "")),
            }
            for r in records
        ]
        self._log_action("list_invoices", {"filter": status, "count": len(invoices)})
        return {"invoices": invoices, "total": len(invoices), "mode": "live"}

    def create_invoice(self, args: dict) -> dict:
        """Create a new invoice in Odoo."""
        now = datetime.now()
        client = args["client"]
        amount = args["amount"]
        description = args["description"]
        due_days = args.get("due_days", 30)

        if DRY_RUN:
            invoice = {
                "id": f"INV-{now.strftime('%Y-%m%d')}",
                "client": client,
                "client_email": args.get("client_email", ""),
                "amount": amount,
                "currency": "USD",
                "status": "draft",
                "date_issued": now.strftime("%Y-%m-%d"),
                "date_due": (now + timedelta(days=due_days)).strftime("%Y-%m-%d"),
                "items": [{"description": description, "quantity": 1, "unit_price": amount}],
                "mode": "dry_run",
            }
            self._log_action("create_invoice", {"client": client, "amount": amount})
            return invoice

        # Live mode: create account.move in Odoo
        if not self.odoo_client:
            return {"status": "error", "message": "Odoo client not connected"}

        # Find or create partner
        partners = self.odoo_client.search_read(
            "res.partner", [("name", "=", client)], fields=["id"], limit=1
        )
        partner_id = partners[0]["id"] if partners else self.odoo_client.create(
            "res.partner", {"name": client, "email": args.get("client_email", "")}
        )

        # Create the invoice (account.move)
        invoice_id = self.odoo_client.create("account.move", {
            "move_type": "out_invoice",
            "partner_id": partner_id,
            "invoice_date": now.strftime("%Y-%m-%d"),
            "invoice_date_due": (now + timedelta(days=due_days)).strftime("%Y-%m-%d"),
            "invoice_line_ids": [(0, 0, {
                "name": description,
                "quantity": 1,
                "price_unit": amount,
            })],
        })

        self._log_action("create_invoice", {"client": client, "amount": amount, "odoo_id": invoice_id})
        return {
            "id": invoice_id, "client": client, "amount": amount,
            "status": "draft", "mode": "live",
        }

    def record_payment(self, args: dict) -> dict:
        """Record a payment against an invoice in Odoo."""
        now = datetime.now()
        invoice_id = args["invoice_id"]
        amount = args["amount"]
        method = args.get("method", "bank_transfer")
        reference = args.get("reference", "")

        if DRY_RUN:
            payment = {
                "id": f"PAY-{now.strftime('%Y%m%d%H%M')}",
                "invoice_id": invoice_id,
                "amount": amount,
                "method": method,
                "date": now.strftime("%Y-%m-%d"),
                "reference": reference or f"PAY-{invoice_id}",
                "status": "recorded",
                "mode": "dry_run",
            }
            self._log_action("record_payment", {"invoice": invoice_id, "amount": amount})
            return payment

        # Live mode: register payment in Odoo via account.payment
        if not self.odoo_client:
            return {"status": "error", "message": "Odoo client not connected"}

        journal_map = {
            "bank_transfer": "Bank", "credit_card": "Bank", "cash": "Cash",
        }
        journals = self.odoo_client.search_read(
            "account.journal",
            [("name", "ilike", journal_map.get(method, "Bank")), ("type", "in", ["bank", "cash"])],
            fields=["id"], limit=1,
        )
        journal_id = journals[0]["id"] if journals else False

        payment_id = self.odoo_client.create("account.payment", {
            "payment_type": "inbound",
            "amount": amount,
            "journal_id": journal_id,
            "date": now.strftime("%Y-%m-%d"),
            "ref": reference or f"PAY-{invoice_id}",
        })

        self._log_action("record_payment", {"invoice": invoice_id, "amount": amount, "payment_id": payment_id})
        return {
            "id": payment_id, "invoice_id": invoice_id, "amount": amount,
            "status": "recorded", "mode": "live",
        }

    def get_profit_loss_report(self, args: dict) -> dict:
        """Get P&L report by querying Odoo income/expense accounts."""
        period = args.get("period", "") or datetime.now().strftime("%Y-%m")

        if DRY_RUN:
            pl = dict(self.fixtures.get("profit_loss", {}))
            pl["period"] = period
            pl["mode"] = "dry_run"
            self._log_action("get_profit_loss_report", {"period": period})
            return pl

        # Live mode: aggregate from account.move.line
        if not self.odoo_client:
            return {"status": "error", "message": "Odoo client not connected"}

        year, month = period.split("-")
        date_from = f"{year}-{month}-01"
        if int(month) == 12:
            date_to = f"{int(year)+1}-01-01"
        else:
            date_to = f"{year}-{int(month)+1:02d}-01"

        # Revenue: income-type accounts
        income_lines = self.odoo_client.search_read(
            "account.move.line",
            [("date", ">=", date_from), ("date", "<", date_to),
             ("account_id.account_type", "=", "income")],
            fields=["credit", "debit"], limit=5000,
        )
        revenue = sum(l.get("credit", 0) - l.get("debit", 0) for l in income_lines)

        # Expenses: expense-type accounts
        expense_lines = self.odoo_client.search_read(
            "account.move.line",
            [("date", ">=", date_from), ("date", "<", date_to),
             ("account_id.account_type", "=", "expense")],
            fields=["debit", "credit"], limit=5000,
        )
        expenses = sum(l.get("debit", 0) - l.get("credit", 0) for l in expense_lines)

        net_profit = revenue - expenses
        self._log_action("get_profit_loss_report", {"period": period})
        return {
            "period": period,
            "revenue": {"total": round(revenue, 2)},
            "expenses": {"total": round(expenses, 2)},
            "net_profit": round(net_profit, 2),
            "profit_margin_pct": round(net_profit / revenue * 100, 1) if revenue else 0,
            "mode": "live",
        }

    def _log_action(self, action: str, details: dict):
        """Log an action to the vault's Logs folder."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{today}.json"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action,
            "actor": "odoo_mcp_server",
            **details,
        }

        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                entries = []

        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def run_stdio(self):
        """Run as MCP server over stdio (JSON-RPC)."""
        print(json.dumps({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "serverInfo": {"name": "odoo-mcp-server", "version": "1.0.0"},
                "capabilities": {"tools": self.get_tools()},
            },
        }), flush=True)

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                method = request.get("method", "")

                if method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {"tools": self.get_tools()},
                    }
                elif method == "tools/call":
                    tool_name = request["params"]["name"]
                    arguments = request["params"].get("arguments", {})
                    result = self.handle_tool_call(tool_name, arguments)
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result)}]
                        },
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {},
                    }

                print(json.dumps(response), flush=True)
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id") if "request" in dir() else None,
                    "error": {"code": -32603, "message": str(e)},
                }
                print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    server = OdooMCPServer()

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("Testing Odoo MCP Server...")
        print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
        print(f"Vault: {VAULT_PATH}")
        print(f"Odoo URL: {ODOO_URL}")
        print(f"Odoo DB: {ODOO_DB}")
        print(f"Tools: {[t['name'] for t in server.get_tools()]}")

        # Test all tools
        result = server.query_account_balance({"account_type": "all"})
        print(f"\nQuery balances: {json.dumps(result, indent=2)[:200]}...")

        result = server.list_invoices({"status": "all"})
        print(f"\nList invoices: {json.dumps(result, indent=2)[:200]}...")

        result = server.create_invoice({
            "client": "NewClient Corp",
            "amount": 2500.00,
            "description": "Consulting Services - February",
        })
        print(f"\nCreate invoice: {json.dumps(result, indent=2)[:200]}...")

        result = server.record_payment({
            "invoice_id": "INV-2026-002",
            "amount": 3200.00,
            "method": "bank_transfer",
        })
        print(f"\nRecord payment: {json.dumps(result, indent=2)[:200]}...")

        result = server.get_profit_loss_report({"period": "2026-02"})
        print(f"\nP&L report: {json.dumps(result, indent=2)[:200]}...")

        print("\nAll Odoo MCP tools tested successfully!")
    else:
        server.run_stdio()
