"""
Gmail Watcher — Monitors Gmail for unread important emails.

Creates action files in /Needs_Action for Claude to process.
Supports dry-run mode (default) for safe development.

Usage:
    python gmail_watcher.py [--vault-path PATH] [--interval SECONDS] [--live]

Requires:
    - Google OAuth2 credentials (credentials.json)
    - Gmail API enabled in Google Cloud Console
    - pip install google-auth google-auth-oauthlib google-api-python-client
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from base_watcher import BaseWatcher

# Dry-run mode by default — set DRY_RUN=false or use --live flag
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"


class GmailWatcher(BaseWatcher):
    """Watches Gmail for unread important emails and creates action files."""

    def __init__(self, vault_path: str, credentials_path: str = None, check_interval: int = 120):
        super().__init__(vault_path, check_interval)
        self.credentials_path = credentials_path
        self.processed_ids = set()
        self.service = None

        if not DRY_RUN and credentials_path:
            self._init_gmail_service()

    def _init_gmail_service(self):
        """Initialize Gmail API service with OAuth2 credentials."""
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
            creds = None
            token_path = Path(self.credentials_path).parent / "token.json"

            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                token_path.write_text(creds.to_json())

            self.service = build("gmail", "v1", credentials=creds)
            self.logger.info("Gmail API service initialized successfully")
        except ImportError:
            self.logger.warning(
                "Google API libraries not installed. Install with: "
                "pip install google-auth google-auth-oauthlib google-api-python-client"
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Gmail API: {e}")

    def check_for_updates(self) -> list:
        """Check for unread important emails."""
        if DRY_RUN:
            return self._check_dry_run()

        if not self.service:
            return []

        try:
            results = self.service.users().messages().list(
                userId="me", q="is:unread is:important", maxResults=10
            ).execute()
            messages = results.get("messages", [])
            return [m for m in messages if m["id"] not in self.processed_ids]
        except Exception as e:
            self.logger.error(f"Gmail API error: {e}")
            return []

    def _check_dry_run(self) -> list:
        """Simulate email checks in dry-run mode using a drop folder."""
        drop_folder = self.vault_path / "Inbox" / "email_drops"
        drop_folder.mkdir(parents=True, exist_ok=True)

        new_items = []
        for f in drop_folder.iterdir():
            if f.is_file() and f.suffix in (".txt", ".md", ".json"):
                file_id = f.stem
                if file_id not in self.processed_ids:
                    try:
                        content = f.read_text(encoding="utf-8")
                        new_items.append({
                            "id": file_id,
                            "from": "simulated@example.com",
                            "subject": f.stem.replace("_", " ").title(),
                            "snippet": content[:200],
                            "source_file": str(f),
                        })
                    except Exception as e:
                        self.logger.error(f"Error reading drop file {f.name}: {e}")
        return new_items

    def create_action_file(self, item) -> Path:
        """Create an action .md file from an email."""
        if DRY_RUN:
            return self._create_dry_run_action(item)

        # Live mode — fetch full email from Gmail API
        try:
            msg = self.service.users().messages().get(
                userId="me", id=item["id"]
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            sender = headers.get("From", "Unknown")
            subject = headers.get("Subject", "No Subject")
            snippet = msg.get("snippet", "")
        except Exception as e:
            self.logger.error(f"Failed to fetch email {item['id']}: {e}")
            return Path()

        return self._write_action_file(item["id"], sender, subject, snippet)

    def _create_dry_run_action(self, item) -> Path:
        """Create action file from simulated email data."""
        return self._write_action_file(
            item["id"],
            item.get("from", "unknown@example.com"),
            item.get("subject", "No Subject"),
            item.get("snippet", ""),
        )

    def _write_action_file(self, email_id, sender, subject, snippet) -> Path:
        """Write the standardized action file."""
        now = datetime.now()
        content = f"""---
type: email
from: {sender}
subject: {subject}
received: {now.isoformat()}
priority: high
status: pending
---

## Email Content
{snippet}

## Suggested Actions
- [ ] Reply to sender
- [ ] Forward to relevant party
- [ ] Archive after processing
"""
        filepath = self.needs_action / f"EMAIL_{email_id}_{now.strftime('%Y%m%d%H%M%S')}.md"
        filepath.write_text(content, encoding="utf-8")
        self.processed_ids.add(email_id)
        self.logger.info(f"[{'DRY RUN' if DRY_RUN else 'LIVE'}] Email action: {filepath.name}")
        return filepath


def main():
    parser = argparse.ArgumentParser(description="Gmail Watcher for AI Employee")
    parser.add_argument(
        "--vault-path",
        default=str(Path(__file__).parent / "AI_Employee_Vault"),
        help="Path to the Obsidian vault",
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="Path to Gmail OAuth2 credentials.json",
    )
    parser.add_argument("--interval", type=int, default=120, help="Check interval in seconds")
    parser.add_argument("--live", action="store_true", help="Disable dry-run mode")
    args = parser.parse_args()

    global DRY_RUN
    if args.live:
        DRY_RUN = False

    print("=" * 50)
    print("  Gmail Watcher — AI Employee")
    print(f"  Mode: {'LIVE' if not DRY_RUN else 'DRY RUN (simulated)'}")
    print(f"  Vault: {args.vault_path}")
    print(f"  Interval: {args.interval}s")
    print("=" * 50)

    watcher = GmailWatcher(args.vault_path, args.credentials, args.interval)
    watcher.run()


if __name__ == "__main__":
    main()
