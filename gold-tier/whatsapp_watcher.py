"""
WhatsApp Watcher — Monitors WhatsApp Web for unread messages containing keywords.

Uses Playwright for browser automation against WhatsApp Web.
Detects messages with business-relevant keywords (urgent, invoice, payment, etc.)
and creates action files in /Needs_Action for Claude to process.

Supports dry-run mode (default) for safe development.
In dry-run mode, reads simulated messages from a drop folder.

Usage:
    python whatsapp_watcher.py [--vault-path PATH] [--interval SECONDS] [--live]

Live mode requires:
    - pip install playwright
    - python -m playwright install chromium
    - A valid WhatsApp Web session (scan QR code on first run)

Note: WhatsApp Web automation should comply with WhatsApp's terms of service.
Use responsibly and at your own discretion.
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from base_watcher import BaseWatcher

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# Keywords that trigger the watcher to capture a message
DEFAULT_KEYWORDS = [
    "urgent", "asap", "invoice", "payment", "help",
    "deadline", "meeting", "quote", "proposal", "contract",
    "order", "delivery", "issue", "problem", "update",
]


class WhatsAppWatcher(BaseWatcher):
    """Watches WhatsApp Web for unread messages matching business keywords."""

    def __init__(
        self,
        vault_path: str,
        session_path: str = None,
        check_interval: int = 30,
        keywords: list = None,
    ):
        super().__init__(vault_path, check_interval)
        self.session_path = Path(session_path) if session_path else self.vault_path.parent / "whatsapp_session"
        self.keywords = keywords or DEFAULT_KEYWORDS
        self.processed_ids = set()

        # Drop folder for dry-run simulation
        self.drop_folder = self.vault_path / "Inbox" / "whatsapp_drops"
        self.drop_folder.mkdir(parents=True, exist_ok=True)

    def check_for_updates(self) -> list:
        """Check for new WhatsApp messages matching keywords."""
        if DRY_RUN:
            return self._check_dry_run()
        return self._check_live()

    def _check_dry_run(self) -> list:
        """Simulate WhatsApp checks using a drop folder.

        Drop .txt, .md, or .json files into AI_Employee_Vault/Inbox/whatsapp_drops/
        to simulate incoming WhatsApp messages.

        JSON format (optional):
        {
            "from": "Client Name",
            "phone": "+1234567890",
            "text": "Hey, can you send the invoice?",
            "group": null
        }
        """
        items = []
        for f in self.drop_folder.iterdir():
            if not f.is_file() or f.suffix not in (".txt", ".md", ".json"):
                continue

            file_id = f.stem
            if file_id in self.processed_ids:
                continue

            try:
                content = f.read_text(encoding="utf-8")

                # Parse JSON messages or treat as plain text
                if f.suffix == ".json":
                    data = json.loads(content)
                    sender = data.get("from", "Unknown Contact")
                    phone = data.get("phone", "+0000000000")
                    text = data.get("text", "")
                    group = data.get("group", None)
                else:
                    # Plain text: first line is sender, rest is message
                    lines = content.strip().splitlines()
                    sender = lines[0] if lines else "Unknown Contact"
                    text = "\n".join(lines[1:]).strip() if len(lines) > 1 else content
                    phone = "+0000000000"
                    group = None

                # Check if message contains any keyword
                text_lower = text.lower()
                matched_keywords = [kw for kw in self.keywords if kw in text_lower]

                if matched_keywords:
                    items.append({
                        "id": file_id,
                        "from": sender,
                        "phone": phone,
                        "text": text,
                        "group": group,
                        "matched_keywords": matched_keywords,
                        "source_file": str(f),
                    })
                    self.logger.info(
                        f"[DRY RUN] Message from {sender} matched: {matched_keywords}"
                    )
            except Exception as e:
                self.logger.error(f"Error reading drop file {f.name}: {e}")

        return items

    def _check_live(self) -> list:
        """Check WhatsApp Web for unread messages using Playwright."""
        items = []
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.logger.error(
                "Playwright not installed. Install with: "
                "pip install playwright && python -m playwright install chromium"
            )
            return items

        try:
            with sync_playwright() as p:
                # Use persistent context to keep WhatsApp session
                self.session_path.mkdir(parents=True, exist_ok=True)
                browser = p.chromium.launch_persistent_context(
                    str(self.session_path), headless=True
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.goto("https://web.whatsapp.com")

                # Wait for chat list to load (may need QR scan on first run)
                try:
                    page.wait_for_selector(
                        '[data-testid="chat-list"]', timeout=60000
                    )
                except Exception:
                    self.logger.warning(
                        "WhatsApp Web not loaded. You may need to scan the QR code. "
                        "Run with headless=False for first-time setup."
                    )
                    browser.close()
                    return items

                # Find chats with unread messages
                unread_chats = page.query_selector_all('[aria-label*="unread"]')

                for chat in unread_chats:
                    try:
                        chat_text = chat.inner_text().lower()

                        # Check for keyword matches
                        matched_keywords = [
                            kw for kw in self.keywords if kw in chat_text
                        ]

                        if matched_keywords:
                            # Extract sender name from chat element
                            name_el = chat.query_selector("span[title]")
                            sender = name_el.get_attribute("title") if name_el else "Unknown"

                            # Generate unique ID from sender + timestamp
                            msg_id = f"{sender}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

                            if msg_id not in self.processed_ids:
                                items.append({
                                    "id": msg_id,
                                    "from": sender,
                                    "phone": "",
                                    "text": chat_text[:500],
                                    "group": None,
                                    "matched_keywords": matched_keywords,
                                    "source_file": "whatsapp_web",
                                })
                    except Exception as e:
                        self.logger.error(f"Error processing chat: {e}")

                browser.close()

        except Exception as e:
            self.logger.error(f"Playwright error: {e}")

        return items

    def create_action_file(self, item) -> Path:
        """Create an action .md file from a WhatsApp message."""
        now = datetime.now()
        keywords_str = ", ".join(item.get("matched_keywords", []))
        group_line = f"group: {item['group']}" if item.get("group") else "group: direct_message"

        # Determine priority based on keywords
        high_priority_kw = {"urgent", "asap", "payment", "problem", "issue"}
        matched = set(item.get("matched_keywords", []))
        priority = "high" if matched & high_priority_kw else "medium"

        content = f"""---
type: whatsapp_message
from: {item['from']}
phone: {item.get('phone', 'unknown')}
{group_line}
received: {now.isoformat()}
priority: {priority}
matched_keywords: {keywords_str}
status: pending
---

## WhatsApp Message

**From:** {item['from']}
**Received:** {now.strftime('%Y-%m-%d %H:%M')}
**Priority:** {priority}
**Keywords matched:** {keywords_str}

### Message Content
{item['text']}

## Suggested Actions
- [ ] Read and understand the message
- [ ] Draft a reply
- [ ] Reply to sender (REQUIRES APPROVAL)
- [ ] Archive after processing
"""
        # Create the action file
        safe_sender = "".join(c if c.isalnum() or c == "_" else "_" for c in item["from"])
        filepath = self.needs_action / f"WHATSAPP_{safe_sender}_{now.strftime('%Y%m%d%H%M%S')}.md"
        filepath.write_text(content, encoding="utf-8")
        self.processed_ids.add(item["id"])

        # Create approval request for reply (HITL)
        self._create_reply_approval(item, filepath)

        self.logger.info(
            f"[{'DRY RUN' if DRY_RUN else 'LIVE'}] WhatsApp action: {filepath.name} "
            f"(from: {item['from']}, keywords: {keywords_str})"
        )
        return filepath

    def _create_reply_approval(self, item, action_filepath: Path):
        """Create a HITL approval request for replying to a WhatsApp message."""
        now = datetime.now()
        approval_dir = self.vault_path / "Pending_Approval"
        approval_dir.mkdir(parents=True, exist_ok=True)

        safe_sender = "".join(c if c.isalnum() or c == "_" else "_" for c in item["from"])
        approval_content = f"""---
type: approval_request
action: whatsapp_reply
to: {item['from']}
phone: {item.get('phone', 'unknown')}
created: {now.isoformat()}
expires: {now.strftime('%Y-%m-%d')}T23:59:59Z
status: pending
related_file: {action_filepath.name}
---

## WhatsApp Reply — Approval Required

### Original Message
**From:** {item['from']}
**Message:** {item['text'][:300]}

### Suggested Reply
_Draft a reply here or let Claude generate one._

### To Approve
Move this file to the `/Approved` folder.

### To Reject
Move this file to the `/Rejected` folder.
"""
        approval_file = approval_dir / f"APPROVE_WHATSAPP_{safe_sender}_{now.strftime('%Y%m%d%H%M%S')}.md"
        approval_file.write_text(approval_content, encoding="utf-8")
        self.logger.info(f"Approval request created: {approval_file.name}")


def main():
    parser = argparse.ArgumentParser(description="WhatsApp Watcher for AI Employee")
    parser.add_argument(
        "--vault-path",
        default=str(Path(__file__).parent / "AI_Employee_Vault"),
        help="Path to the Obsidian vault",
    )
    parser.add_argument(
        "--session-path",
        default=None,
        help="Path to store WhatsApp Web browser session",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Check interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=None,
        help="Custom keywords to watch for (space-separated)",
    )
    parser.add_argument("--live", action="store_true", help="Disable dry-run mode")
    args = parser.parse_args()

    global DRY_RUN
    if args.live:
        DRY_RUN = False

    print("=" * 55)
    print("  WhatsApp Watcher — AI Employee")
    print(f"  Mode: {'LIVE (Playwright)' if not DRY_RUN else 'DRY RUN (simulated)'}")
    print(f"  Vault: {args.vault_path}")
    print(f"  Interval: {args.interval}s")
    keywords = args.keywords or DEFAULT_KEYWORDS
    print(f"  Keywords: {', '.join(keywords[:8])}{'...' if len(keywords) > 8 else ''}")
    if DRY_RUN:
        drop = Path(args.vault_path) / "Inbox" / "whatsapp_drops"
        print(f"  Drop folder: {drop}")
    print("=" * 55)

    watcher = WhatsAppWatcher(
        args.vault_path,
        session_path=args.session_path,
        check_interval=args.interval,
        keywords=keywords,
    )
    watcher.run()


if __name__ == "__main__":
    main()
