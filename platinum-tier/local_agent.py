"""
Local Agent — Local-side Approval Executor (Platinum Tier).

Runs on the user's local machine (laptop / home server).
Complements the Cloud Agent — handles all sensitive/privileged actions
that Cloud must NEVER do.

Work-Zone Specialization (Platinum Rule):
  LOCAL OWNS:
    - Approvals: review and execute cloud-drafted actions
    - WhatsApp session and replies (never on cloud)
    - Banking, payments, payment token execution
    - Final "send/post" — email send, social post, Odoo invoice posting
    - Dashboard.md updates (single-writer rule — only Local writes it)
    - Merging /Updates/ from cloud into Dashboard.md

  CLOUD OWNS (never done here, just executed):
    - Email triage & draft creation
    - Social post drafts
    - Odoo draft invoice creation
    - Vault sync pull/push

Usage:
    python local_agent.py [--vault-path PATH] [--interval SECONDS]

The local agent:
  1. Pulls latest vault state from git (cloud may have pushed new drafts)
  2. Merges /Updates/ signals from cloud into Dashboard.md
  3. Checks health of cloud agent (/Signals/health.md)
  4. Watches /Approved/ — executes any approved actions
  5. Updates Dashboard.md with current state
  6. Handles WhatsApp triage (local-only watcher)
  7. Pushes local vault state
"""

import os
import sys
import time
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from vault_sync import VaultSync
from platinum_skills import (
    LocalApprovalExecutorSkill,
    DashboardMergeSkill,
    CloudHealthMonitorSkill,
    VaultCleanupSkill,
    PLATINUM_SKILLS,
)
from agent_skills import (
    SkillRegistry,
    UpdateDashboardSkill,
    WhatsAppReplySkill,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LocalAgent] %(levelname)s: %(message)s",
)
logger = logging.getLogger("LocalAgent")

AGENT_ID = os.environ.get("AGENT_ID", "local-agent")
os.environ["AGENT_ID"] = AGENT_ID


class LocalAgent:
    """
    Platinum Tier Local-side orchestrator.

    Cycle (every N seconds):
      1. Pull vault state from git (get cloud drafts/approvals)
      2. Merge /Updates/ from cloud into Dashboard.md
      3. Check cloud agent health via /Signals/health.md
      4. Execute approved actions from /Approved/
      5. Update Dashboard.md (single writer)
      6. Handle local-only tasks (WhatsApp)
      7. Push vault state
    """

    def __init__(self, vault_path: str, check_interval: int = 30):
        self.vault_path = Path(vault_path)
        self.check_interval = check_interval

        # Vault directories
        self.needs_action = self.vault_path / "Needs_Action"
        self.pending_approval = self.vault_path / "Pending_Approval"
        self.approved = self.vault_path / "Approved"
        self.rejected = self.vault_path / "Rejected"
        self.done = self.vault_path / "Done"
        self.plans = self.vault_path / "Plans"
        self.inbox = self.vault_path / "Inbox"
        self.logs_dir = self.vault_path / "Logs"
        self.updates = self.vault_path / "Updates"
        self.signals = self.vault_path / "Signals"
        self.in_progress = self.vault_path / "In_Progress" / AGENT_ID
        self.system_logs = self.vault_path / "System_Logs.md"
        self.dashboard = self.vault_path / "Dashboard.md"

        # Create directories
        for d in [
            self.needs_action, self.pending_approval, self.approved,
            self.rejected, self.done, self.plans, self.inbox, self.logs_dir,
            self.updates, self.signals, self.in_progress,
            self.vault_path / "In_Progress",
            self.needs_action / "cloud",
            self.needs_action / "local",
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Initialize vault sync
        self.vault_sync = VaultSync(repo_dir=str(self.vault_path.parent))
        self.vault_sync.ensure_gitignore()

        # Build vault paths dict
        vault_paths = self._build_vault_paths()

        # Skill instances
        self.approval_executor = LocalApprovalExecutorSkill(vault_paths)
        self.dashboard_merge = DashboardMergeSkill(vault_paths)
        self.health_checker = CloudHealthMonitorSkill(vault_paths)
        self.cleanup_skill = VaultCleanupSkill(vault_paths)
        self.update_dashboard = UpdateDashboardSkill(vault_paths)

        self.processed_approvals = set()
        self.running = False
        self.cycle_count = 0

    def _build_vault_paths(self) -> dict:
        return {
            "vault": self.vault_path,
            "inbox": self.inbox,
            "needs_action": self.needs_action,
            "done": self.done,
            "system_logs": self.system_logs,
            "dashboard": self.dashboard,
            "plans": self.plans,
            "pending_approval": self.pending_approval,
            "approved": self.approved,
            "rejected": self.rejected,
            "logs_dir": self.logs_dir,
        }

    def log(self, message: str):
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
        entry = f"| {timestamp} | [LOCAL] {message} |\n"
        with open(self.system_logs, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(message)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        self.running = True
        self.log(f"Local Agent started (ID: {AGENT_ID}, interval: {self.check_interval}s)")

        while self.running:
            try:
                self._run_cycle()
            except KeyboardInterrupt:
                self.log("Local Agent shutting down (KeyboardInterrupt)")
                break
            except Exception as e:
                self.log(f"ERROR in cycle: {e}")
                logger.exception("Unhandled error in cycle")

            time.sleep(self.check_interval)

    def _run_cycle(self):
        self.cycle_count += 1
        self.log(f"=== Cycle #{self.cycle_count} ===")

        # Step 1: Pull vault (get cloud's latest drafts)
        pull = self.vault_sync.pull()
        if pull["status"] == "error":
            self.log(f"Vault pull warning: {pull['output']}")

        # Step 2: Merge cloud Updates into Dashboard.md (LOCAL is single writer)
        self.dashboard_merge.execute()

        # Step 3: Check cloud agent health
        health = self.health_checker.check_stale()
        if health.get("status") == "stale":
            self.log(f"ALERT: Cloud agent is stale ({health.get('age_minutes', '?'):.1f} min)")
            self._write_health_alert(health)

        # Step 4: Execute approved actions
        self._process_approved()

        # Step 5: Cleanup stale claims
        cleanup = self.cleanup_skill.execute()
        if cleanup.get("reclaimed", 0) > 0:
            self.log(f"Reclaimed {cleanup['reclaimed']} stale In_Progress claim(s)")

        # Step 6: Update Dashboard.md (single-writer rule — Local only)
        self._update_dashboard()

        # Step 7: Push vault state
        push = self.vault_sync.push(f"Local Agent cycle #{self.cycle_count}: approvals + dashboard")
        if push["status"] == "error":
            self.log(f"Vault push warning: {push['output']}")

    def _process_approved(self):
        """Execute all files in /Approved/ folder."""
        if not self.approved.exists():
            return

        for approval_file in list(self.approved.iterdir()):
            if not approval_file.is_file():
                continue
            if approval_file.name in self.processed_approvals:
                continue

            self.log(f"Executing approved action: {approval_file.name}")
            self.processed_approvals.add(approval_file.name)

            try:
                result = self.approval_executor.execute(approval_file)
                if result.get("status") in ("success", "simulated"):
                    self.log(f"Action executed: {approval_file.name} → {result.get('status')}")
                else:
                    self.log(f"Action failed: {approval_file.name} → {result}")
                    # Move back to pending_approval on failure
                    dest = self.pending_approval / f"FAILED_{approval_file.name}"
                    if approval_file.exists():
                        shutil.move(str(approval_file), str(dest))
            except Exception as e:
                self.log(f"Error executing {approval_file.name}: {e}")

    def _update_dashboard(self):
        """Update Dashboard.md with current vault state (Local is single writer)."""
        try:
            # Count files in each directory
            counts = {}
            for folder, key in [
                (self.inbox, "Inbox"),
                (self.needs_action, "Needs_Action"),
                (self.done, "Done"),
                (self.plans, "Plans"),
                (self.pending_approval, "Pending_Approval"),
                (self.approved, "Approved"),
                (self.rejected, "Rejected"),
            ]:
                counts[key] = len(list(folder.glob("*"))) if folder.exists() else 0

            # Check cloud health
            health = self.health_checker.check_stale()
            cloud_status = health.get("status", "unknown").upper()
            cloud_age = health.get("age_minutes", 0)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

            dashboard_content = (
                f"# Dashboard — AI Employee Vault (Platinum Tier)\n\n"
                f"## System Status\n\n"
                f"| Field | Value |\n|---|---|\n"
                f"| **Status** | ONLINE |\n"
                f"| **Tier** | Platinum |\n"
                f"| **Last Updated** | {timestamp} |\n"
                f"| **Local Agent** | ONLINE |\n"
                f"| **Cloud Agent** | {cloud_status} ({cloud_age:.0f} min ago) |\n"
                f"| **Total Completed** | {counts.get('Done', 0)} |\n\n"
                f"## File Counts\n\n"
                f"| Folder | Count |\n|---|---|\n"
            )
            for key, count in counts.items():
                dashboard_content += f"| {key.replace('_', ' ')} | {count} |\n"

            dashboard_content += (
                f"\n## Approval Queue\n\n"
                f"| Status | Count |\n|---|---|\n"
                f"| Pending | {counts.get('Pending_Approval', 0)} |\n"
                f"| Approved | {counts.get('Approved', 0)} |\n"
                f"| Rejected | {counts.get('Rejected', 0)} |\n\n"
                f"## Platinum Tier Work-Zone Split\n\n"
                f"| Zone | Owns |\n|---|---|\n"
                f"| **Cloud (24/7)** | Email triage, draft replies, social drafts, Odoo drafts |\n"
                f"| **Local (on-demand)** | Approvals, WhatsApp, payments, final send/post |\n\n"
                f"*Written by Local Agent (single-writer rule). "
                f"Cloud writes to /Updates/ — merged here.*\n"
            )

            self.dashboard.write_text(dashboard_content, encoding="utf-8")
            self.log("Dashboard.md updated")

        except Exception as e:
            self.log(f"Dashboard update failed: {e}")

    def _write_health_alert(self, health: dict):
        """Write alert to /Signals/alert.md when cloud is stale."""
        alert_path = self.signals / "alert.md"
        age = health.get("age_minutes", "?")
        alert_path.write_text(
            f"---\ntype: alert\ntimestamp: {datetime.now().isoformat()}\n---\n\n"
            f"# Cloud Agent Health Alert\n\n"
            f"Cloud agent heartbeat is **{age:.1f} minutes old** (threshold: 10 min).\n\n"
            f"Please check the cloud VM.\n",
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Platinum Demo: simulate the offline-to-approval flow
# ---------------------------------------------------------------------------

def run_platinum_demo(vault_path: str):
    """
    Demonstrate the Platinum minimum passing gate:
      Email arrives while Local is offline
        → Cloud drafts reply + writes Pending_Approval file
        → Local returns, user approves (moves file to /Approved/)
        → Local executes send via MCP
        → Logs
        → Moves to /Done/

    Run this once to populate demo files, then approve manually.
    """
    vault = Path(vault_path)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Simulate email arriving (as if Cloud agent wrote this)
    email_task = vault / "Needs_Action" / f"DEMO_EMAIL_{timestamp}.md"
    email_task.write_text(
        f"---\ntype: email\nfrom: demo.client@example.com\n"
        f"subject: Platinum Demo — Invoice Request\n"
        f"received: {datetime.now().isoformat()}\npriority: high\nstatus: pending\n---\n\n"
        f"## Email Content\n\nHi, I need an invoice for the consulting work done last month.\n"
        f"Please send it to demo.client@example.com.\n\n"
        f"## Suggested Actions\n- [ ] Reply to sender\n- [ ] Create invoice in Odoo\n",
        encoding="utf-8",
    )

    print(f"[PlatinumDemo] Created email task: {email_task.name}")
    print(f"[PlatinumDemo] Run cloud_agent.py to draft reply → Pending_Approval/")
    print(f"[PlatinumDemo] Then approve by moving the approval file to Approved/")
    print(f"[PlatinumDemo] Then run local_agent.py to execute the send")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AI Employee — Local Agent (Platinum Tier)")
    parser.add_argument(
        "--vault-path",
        default=os.environ.get("VAULT_PATH", "AI_Employee_Vault"),
        help="Path to the AI Employee Vault",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("LOCAL_AGENT_INTERVAL", "30")),
        help="Check interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the Platinum demo (creates sample email task)",
    )
    args = parser.parse_args()

    if args.demo:
        run_platinum_demo(args.vault_path)
        return

    agent = LocalAgent(vault_path=args.vault_path, check_interval=args.interval)
    agent.run()


if __name__ == "__main__":
    main()
