"""
LinkedIn Watcher — Monitors LinkedIn and auto-posts business content.

Supports two modes:
1. Watching for new notifications/messages (inbound)
2. Auto-posting business content to LinkedIn (outbound)

Uses dry-run mode by default for safe development.
In live mode, uses Playwright browser automation (like WhatsApp watcher).

Usage:
    python linkedin_watcher.py [--vault-path PATH] [--interval SECONDS] [--live]

    # First time: login via browser (one-time, session saved)
    python linkedin_watcher.py --auth

Live mode requires:
    - pip install playwright
    - python -m playwright install chromium
    - Run --auth once (opens browser, you log into LinkedIn, session saved)
    - No developer app or API credentials needed
"""

import os
import json
import argparse
import time
from pathlib import Path
from datetime import datetime
from base_watcher import BaseWatcher

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


class LinkedInBrowser:
    """LinkedIn browser automation using Playwright with persistent session.

    Like the WhatsApp watcher — you log in once in the browser, the session
    cookies are saved to disk, and subsequent runs auto-authenticate.
    No developer credentials or API keys needed.
    """

    def __init__(self, session_path: Path):
        self.session_path = session_path
        self.session_path.mkdir(parents=True, exist_ok=True)

    def is_authenticated(self) -> bool:
        """Check if a saved browser session exists."""
        # Chromium persistent context stores cookies/state in the session dir
        return (self.session_path / "Default").exists()

    def authenticate(self):
        """Open LinkedIn login page in a visible browser. User logs in manually.
        Session is saved automatically for future use.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Install with:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium"
            )

        print("\n  Opening LinkedIn login page...")
        print("  Please log in with your LinkedIn account.")
        print("  After logging in, the session will be saved automatically.")
        print("  Close the browser window when you see your LinkedIn feed.\n")

        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                str(self.session_path),
                headless=False,  # Must be visible for user to log in
                viewport={"width": 1280, "height": 800},
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto("https://www.linkedin.com/login")

            # Wait for the user to log in — detected when URL changes to feed
            print("  Waiting for you to log in...")
            try:
                page.wait_for_url("**/feed**", timeout=120000)
                print("  Login successful! Session saved.")
            except Exception:
                # Also accept other post-login pages
                current_url = page.url
                if "linkedin.com" in current_url and "login" not in current_url:
                    print("  Login successful! Session saved.")
                else:
                    print("  Login timed out. Please try again.")
                    browser.close()
                    return False

            browser.close()
            return True

    def post(self, content: str) -> dict:
        """Post content to LinkedIn using Voyager API with session cookies.

        Extracts cookies from the saved Playwright session and calls
        LinkedIn's internal API directly — no UI automation needed.
        """
        import urllib.request
        import urllib.error

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"status": "error", "error": "Playwright not installed"}

        if not self.is_authenticated():
            return {
                "status": "error",
                "error": "Not logged in. Run: python linkedin_watcher.py --auth",
            }

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    str(self.session_path),
                    headless=True,
                    viewport={"width": 1280, "height": 800},
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
                time.sleep(3)

                # Check if still logged in
                if "login" in page.url.lower():
                    browser.close()
                    return {
                        "status": "error",
                        "error": "Session expired. Run: python linkedin_watcher.py --auth",
                    }

                # Extract cookies for API calls
                cookies = page.context.cookies()
                cookie_dict = {c["name"]: c["value"] for c in cookies}
                csrf_token = cookie_dict.get("JSESSIONID", "").strip('"')
                cookie_str = "; ".join(
                    f'{c["name"]}={c["value"]}' for c in cookies
                )

                browser.close()

            # Post via LinkedIn Voyager API
            payload = json.dumps({
                "visibleToConnectionsOnly": False,
                "externalAudienceProviders": [],
                "commentaryV2": {
                    "text": content,
                    "attributes": [],
                },
                "origin": "FEED",
                "allowedCommentersScope": "ALL",
                "postState": "PUBLISHED",
                "media": [],
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://www.linkedin.com/voyager/api/contentcreation/normShares",
                data=payload,
                headers={
                    "Cookie": cookie_str,
                    "csrf-token": csrf_token,
                    "Content-Type": "application/json",
                    "x-restli-protocol-version": "2.0.0",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                share_urn = resp_data.get("status", {}).get("urn", "")

            return {
                "status": "posted",
                "content": content[:500],
                "share_urn": share_urn,
                "posted_at": datetime.now().isoformat(),
            }

        except urllib.error.HTTPError as e:
            return {
                "status": "error",
                "error": f"LinkedIn API error {e.code}: {e.read().decode()[:200]}",
                "content": content[:200],
                "posted_at": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "content": content[:200],
                "posted_at": datetime.now().isoformat(),
            }


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
        """Post content to LinkedIn (dry-run or live via Playwright browser)."""
        if DRY_RUN:
            self.logger.info(f"[DRY RUN] Would post to LinkedIn: {content[:80]}...")
            result = {
                "status": "dry_run",
                "content": content,
                "posted_at": datetime.now().isoformat(),
            }
        else:
            session_path = self.vault_path.parent / "linkedin_session"
            linkedin = LinkedInBrowser(session_path)

            if not linkedin.is_authenticated():
                self.logger.error(
                    "Not logged in. Run: python linkedin_watcher.py --auth"
                )
                result = {
                    "status": "error",
                    "error": "Not logged in. Run: python linkedin_watcher.py --auth",
                    "content": content,
                    "posted_at": datetime.now().isoformat(),
                }
            else:
                result = linkedin.post(content)
                if result["status"] == "posted":
                    self.logger.info(f"LinkedIn posted successfully: {content[:80]}...")
                else:
                    self.logger.error(f"LinkedIn post failed: {result.get('error')}")

        self.log_to_vault("linkedin_post", json.dumps(result), result["status"])
        return result


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Watcher — AI Employee (Gold Tier)")
    parser.add_argument(
        "--vault-path",
        default=str(Path(__file__).parent / "AI_Employee_Vault"),
        help="Path to the Obsidian vault",
    )
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds")
    parser.add_argument("--live", action="store_true", help="Enable live mode (browser automation)")
    parser.add_argument("--auth", action="store_true", help="One-time LinkedIn login via browser (session saved)")
    args = parser.parse_args()

    global DRY_RUN
    if args.live or args.auth:
        DRY_RUN = False

    session_path = Path(args.vault_path).parent / "linkedin_session"

    # --auth: open browser for one-time login
    if args.auth:
        print("=" * 55)
        print("  LinkedIn Login — AI Employee")
        print("  No developer account or API keys needed!")
        print("=" * 55)
        linkedin = LinkedInBrowser(session_path)
        try:
            success = linkedin.authenticate()
            if success:
                print("\n  You can now run: python linkedin_watcher.py --live")
            else:
                print("\n  Login failed. Please try again.")
        except Exception as e:
            print(f"\n  Login failed: {e}")
        return

    # Normal watcher mode
    linkedin = LinkedInBrowser(session_path)

    print("=" * 55)
    print("  LinkedIn Watcher — AI Employee (Gold Tier)")
    print(f"  Mode: {'LIVE (Playwright)' if not DRY_RUN else 'DRY RUN (simulated)'}")
    print(f"  Vault: {args.vault_path}")
    print(f"  Interval: {args.interval}s")
    if not DRY_RUN:
        if linkedin.is_authenticated():
            print("  Auth: Session found (auto-logged in)")
        else:
            print("  Auth: No session! Run 'python linkedin_watcher.py --auth' first")
    print("=" * 55)

    watcher = LinkedInWatcher(args.vault_path, args.interval)
    watcher.run()


if __name__ == "__main__":
    main()
