"""
LinkedIn Watcher — Monitors LinkedIn and auto-posts business content.

Supports two modes:
1. Watching for new notifications/messages (inbound)
2. Auto-posting business content to LinkedIn (outbound)

Uses dry-run mode by default for safe development.
In live mode, uses LinkedIn API or Playwright for automation.

Usage:
    python linkedin_watcher.py [--vault-path PATH] [--interval SECONDS] [--live]
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from base_watcher import BaseWatcher

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"


class LinkedInWatcher(BaseWatcher):
    """Watches for LinkedIn activity and manages auto-posting."""

    def __init__(self, vault_path: str, check_interval: int = 300):
        super().__init__(vault_path, check_interval)
        self.processed_ids = set()
        self.post_queue_dir = self.vault_path / "Inbox" / "linkedin_posts"
        self.post_queue_dir.mkdir(parents=True, exist_ok=True)
        self.posted_dir = self.vault_path / "Done" / "linkedin_posted"
        self.posted_dir.mkdir(parents=True, exist_ok=True)

    def check_for_updates(self) -> list:
        """Check for new LinkedIn notifications and queued posts."""
        items = []

        # Check for queued posts waiting to be published
        items.extend(self._check_post_queue())

        # Check for inbound notifications (simulated in dry-run)
        items.extend(self._check_notifications())

        return items

    def _check_post_queue(self) -> list:
        """Check for content files queued for LinkedIn posting."""
        items = []
        for f in self.post_queue_dir.iterdir():
            if f.is_file() and f.suffix in (".txt", ".md", ".json"):
                file_id = f.stem
                if file_id not in self.processed_ids:
                    try:
                        content = f.read_text(encoding="utf-8")

                        # If JSON, parse it; otherwise treat as plain text
                        if f.suffix == ".json":
                            data = json.loads(content)
                            post_content = data.get("content", content)
                            hashtags = data.get("hashtags", [])
                        else:
                            post_content = content
                            hashtags = self._extract_hashtags(content)

                        items.append({
                            "id": file_id,
                            "type": "post",
                            "content": post_content,
                            "hashtags": hashtags,
                            "source_file": str(f),
                        })
                    except Exception as e:
                        self.logger.error(f"Error reading post file {f.name}: {e}")
        return items

    def _check_notifications(self) -> list:
        """Check for LinkedIn notifications (simulated in dry-run)."""
        if DRY_RUN:
            # In dry-run, check a notifications drop folder
            notif_dir = self.vault_path / "Inbox" / "linkedin_notifications"
            notif_dir.mkdir(parents=True, exist_ok=True)

            items = []
            for f in notif_dir.iterdir():
                if f.is_file() and f.stem not in self.processed_ids:
                    try:
                        content = f.read_text(encoding="utf-8")
                        items.append({
                            "id": f.stem,
                            "type": "notification",
                            "content": content,
                            "source_file": str(f),
                        })
                    except Exception as e:
                        self.logger.error(f"Error reading notification {f.name}: {e}")
            return items
        return []

    def _extract_hashtags(self, content: str) -> list:
        """Extract hashtags from content text."""
        words = content.split()
        return [w for w in words if w.startswith("#")]

    def create_action_file(self, item) -> Path:
        """Create action file based on item type."""
        if item["type"] == "post":
            return self._create_post_action(item)
        else:
            return self._create_notification_action(item)

    def _create_post_action(self, item) -> Path:
        """Create an action file for a LinkedIn post."""
        now = datetime.now()
        hashtags_str = " ".join(item.get("hashtags", []))

        content = f"""---
type: linkedin_post
status: pending_approval
created: {now.isoformat()}
source: {item.get('source_file', 'unknown')}
---

## LinkedIn Post Content
{item['content']}

## Hashtags
{hashtags_str if hashtags_str else 'No hashtags specified'}

## Post Status
- [ ] Content reviewed
- [ ] Approved for posting
- [ ] Posted to LinkedIn
"""
        filepath = self.needs_action / f"LINKEDIN_POST_{item['id']}_{now.strftime('%Y%m%d%H%M%S')}.md"
        filepath.write_text(content, encoding="utf-8")
        self.processed_ids.add(item["id"])

        # Create approval request for the post
        self._create_approval_request(item, filepath)

        self.logger.info(f"[{'DRY RUN' if DRY_RUN else 'LIVE'}] LinkedIn post queued: {filepath.name}")
        return filepath

    def _create_notification_action(self, item) -> Path:
        """Create an action file for a LinkedIn notification."""
        now = datetime.now()
        content = f"""---
type: linkedin_notification
status: pending
received: {now.isoformat()}
---

## LinkedIn Notification
{item['content']}

## Suggested Actions
- [ ] Review notification
- [ ] Respond if needed
- [ ] Archive
"""
        filepath = self.needs_action / f"LINKEDIN_NOTIF_{item['id']}_{now.strftime('%Y%m%d%H%M%S')}.md"
        filepath.write_text(content, encoding="utf-8")
        self.processed_ids.add(item["id"])
        self.logger.info(f"LinkedIn notification action: {filepath.name}")
        return filepath

    def _create_approval_request(self, item, action_filepath: Path):
        """Create a HITL approval request for LinkedIn post."""
        now = datetime.now()
        approval_content = f"""---
type: approval_request
action: linkedin_post
content_preview: {item['content'][:100]}...
created: {now.isoformat()}
expires: {now.strftime('%Y-%m-%d')}T23:59:59Z
status: pending
related_file: {action_filepath.name}
---

## LinkedIn Post — Approval Required

### Content Preview
{item['content'][:500]}

### To Approve
Move this file to the /Approved folder.

### To Reject
Move this file to the /Rejected folder.
"""
        approval_dir = self.vault_path / "Pending_Approval"
        approval_dir.mkdir(parents=True, exist_ok=True)
        approval_file = approval_dir / f"APPROVE_LINKEDIN_{item['id']}.md"
        approval_file.write_text(approval_content, encoding="utf-8")
        self.logger.info(f"Approval request created: {approval_file.name}")

    def post_to_linkedin(self, content: str) -> dict:
        """Post content to LinkedIn (dry-run or live)."""
        if DRY_RUN:
            self.logger.info(f"[DRY RUN] Would post to LinkedIn: {content[:80]}...")
            result = {
                "status": "dry_run",
                "content": content,
                "posted_at": datetime.now().isoformat(),
            }
        else:
            # In live mode, this would use LinkedIn API or Playwright
            # LinkedIn API requires OAuth2 with w_member_social scope
            self.logger.info("Live LinkedIn posting not configured — using dry-run")
            result = {
                "status": "dry_run",
                "content": content,
                "posted_at": datetime.now().isoformat(),
            }

        self.log_to_vault("linkedin_post", json.dumps(result), result["status"])
        return result


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Watcher for AI Employee")
    parser.add_argument(
        "--vault-path",
        default=str(Path(__file__).parent / "AI_Employee_Vault"),
        help="Path to the Obsidian vault",
    )
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds")
    parser.add_argument("--live", action="store_true", help="Disable dry-run mode")
    args = parser.parse_args()

    global DRY_RUN
    if args.live:
        DRY_RUN = False

    print("=" * 50)
    print("  LinkedIn Watcher — AI Employee")
    print(f"  Mode: {'LIVE' if not DRY_RUN else 'DRY RUN (simulated)'}")
    print(f"  Vault: {args.vault_path}")
    print(f"  Interval: {args.interval}s")
    print("=" * 50)

    watcher = LinkedInWatcher(args.vault_path, args.interval)
    watcher.run()


if __name__ == "__main__":
    main()
