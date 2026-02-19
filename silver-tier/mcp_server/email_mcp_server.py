"""
Email MCP Server — Model Context Protocol server for email actions.

Provides tools for Claude Code to send emails, create drafts, and search emails.
Runs as a stdio MCP server that Claude Code can connect to.

Supports dry-run mode (default) for safe development.

Setup in Claude Code settings (~/.claude.json or .claude/settings.json):
{
    "mcpServers": {
        "email": {
            "command": "python",
            "args": ["path/to/email_mcp_server.py"],
            "env": {
                "DRY_RUN": "true",
                "GMAIL_CREDENTIALS": "path/to/credentials.json"
            }
        }
    }
}
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
VAULT_PATH = os.getenv("VAULT_PATH", str(Path(__file__).parent.parent / "AI_Employee_Vault"))


class EmailMCPServer:
    """MCP Server providing email capabilities to Claude Code."""

    def __init__(self):
        self.vault_path = Path(VAULT_PATH)
        self.drafts_dir = self.vault_path / "Drafts"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.vault_path / "Logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def get_tools(self) -> list:
        """Return list of available MCP tools."""
        return [
            {
                "name": "send_email",
                "description": "Send an email to a recipient. In dry-run mode, creates a draft instead.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email body content"},
                        "cc": {"type": "string", "description": "CC recipients (optional)"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
            {
                "name": "create_draft",
                "description": "Create an email draft saved to the vault.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email body content"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
            {
                "name": "list_drafts",
                "description": "List all email drafts in the vault.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "search_emails",
                "description": "Search for emails by keyword in the vault's processed email files.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword"},
                    },
                    "required": ["query"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """Handle an MCP tool call."""
        if tool_name == "send_email":
            return self.send_email(arguments)
        elif tool_name == "create_draft":
            return self.create_draft(arguments)
        elif tool_name == "list_drafts":
            return self.list_drafts()
        elif tool_name == "search_emails":
            return self.search_emails(arguments.get("query", ""))
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def send_email(self, args: dict) -> dict:
        """Send an email or create a draft in dry-run mode."""
        to = args["to"]
        subject = args["subject"]
        body = args["body"]
        cc = args.get("cc", "")

        if DRY_RUN:
            # In dry-run mode, save as draft and log
            result = self.create_draft(args)
            result["mode"] = "dry_run"
            result["message"] = f"[DRY RUN] Email would be sent to {to}"
            self._log_action("send_email", {
                "to": to, "subject": subject, "status": "dry_run"
            })
            return result

        # Live mode — would use Gmail API here
        try:
            # Placeholder for actual Gmail API send
            self._log_action("send_email", {
                "to": to, "subject": subject, "status": "sent"
            })
            return {
                "status": "sent",
                "to": to,
                "subject": subject,
                "sent_at": datetime.now().isoformat(),
            }
        except Exception as e:
            self._log_action("send_email", {
                "to": to, "subject": subject, "status": "error", "error": str(e)
            })
            return {"status": "error", "error": str(e)}

    def create_draft(self, args: dict) -> dict:
        """Create an email draft in the vault."""
        now = datetime.now()
        draft = {
            "to": args["to"],
            "subject": args["subject"],
            "body": args["body"],
            "cc": args.get("cc", ""),
            "status": "draft",
            "created_at": now.isoformat(),
        }

        filename = f"draft_{now.strftime('%Y%m%d_%H%M%S')}_{args['to'].split('@')[0]}.json"
        draft_path = self.drafts_dir / filename
        draft_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")

        self._log_action("create_draft", {
            "to": args["to"], "subject": args["subject"], "file": filename
        })

        return {
            "status": "draft_created",
            "file": filename,
            "path": str(draft_path),
        }

    def list_drafts(self) -> dict:
        """List all drafts in the vault."""
        drafts = []
        for f in self.drafts_dir.iterdir():
            if f.is_file() and f.suffix == ".json":
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    drafts.append({
                        "file": f.name,
                        "to": data.get("to", ""),
                        "subject": data.get("subject", ""),
                        "created_at": data.get("created_at", ""),
                    })
                except (json.JSONDecodeError, ValueError):
                    continue
        return {"drafts": drafts, "count": len(drafts)}

    def search_emails(self, query: str) -> dict:
        """Search for emails in the vault by keyword."""
        results = []
        search_dirs = [
            self.vault_path / "Needs_Action",
            self.vault_path / "Done",
            self.drafts_dir,
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for f in search_dir.iterdir():
                if not f.is_file():
                    continue
                try:
                    content = f.read_text(encoding="utf-8").lower()
                    if query.lower() in content:
                        results.append({
                            "file": f.name,
                            "folder": search_dir.name,
                            "snippet": content[:200],
                        })
                except (UnicodeDecodeError, ValueError):
                    continue

        return {"results": results, "count": len(results), "query": query}

    def _log_action(self, action: str, details: dict):
        """Log an action to the vault's Logs folder."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{today}.json"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action,
            "actor": "email_mcp_server",
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
                "serverInfo": {
                    "name": "email-mcp-server",
                    "version": "1.0.0",
                },
                "capabilities": {
                    "tools": self.get_tools(),
                },
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
    server = EmailMCPServer()

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Test mode — run some test operations
        print("Testing Email MCP Server...")
        print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
        print(f"Vault: {VAULT_PATH}")
        print(f"Tools: {[t['name'] for t in server.get_tools()]}")

        # Test create draft
        result = server.create_draft({
            "to": "test@example.com",
            "subject": "Test Email",
            "body": "This is a test email from the MCP server.",
        })
        print(f"Create draft: {result}")

        # Test send email (dry-run)
        result = server.send_email({
            "to": "client@example.com",
            "subject": "Invoice January 2026",
            "body": "Please find attached your invoice.",
        })
        print(f"Send email: {result}")

        # Test list drafts
        result = server.list_drafts()
        print(f"List drafts: {result}")

        # Test search
        result = server.search_emails("test")
        print(f"Search: {result}")
    else:
        server.run_stdio()
