"""
Orchestrator — Master process for the AI Employee.

Manages all watchers, monitors folders, handles approval workflows,
and coordinates the reasoning loop. This is the central nervous system.

Usage:
    python orchestrator.py [--vault-path PATH]

Features:
    - Starts and monitors all watcher processes
    - Watches Approved/ folder to execute approved actions
    - Watches Needs_Action/ for new tasks requiring plans
    - Generates daily briefings on schedule
    - Maintains system health
"""

import os
import sys
import json
import time
import shutil
import logging
import argparse
import threading
import subprocess
from pathlib import Path
from datetime import datetime

from agent_skills import (
    SkillRegistry,
    ClassifySkill,
    MoveToeDoneSkill,
    UpdateDashboardSkill,
    TaskPlannerSkill,
    VaultFileManagerSkill,
    VaultWatcherSkill,
    HumanApprovalSkill,
    GmailSendSkill,
    LinkedInPostSkill,
    PlanCreatorSkill,
    ApprovalWatcherSkill,
    SchedulerSkill,
    CEOBriefingSkill,
    LinkedInAutoPostSkill,
    AuditLogSkill,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """Master process that coordinates all AI Employee components."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.needs_action = self.vault_path / "Needs_Action"
        self.pending_approval = self.vault_path / "Pending_Approval"
        self.approved = self.vault_path / "Approved"
        self.rejected = self.vault_path / "Rejected"
        self.done = self.vault_path / "Done"
        self.plans = self.vault_path / "Plans"
        self.inbox = self.vault_path / "Inbox"
        self.logs_dir = self.vault_path / "Logs"
        self.system_logs = self.vault_path / "System_Logs.md"
        self.dashboard = self.vault_path / "Dashboard.md"

        # Ensure all directories exist
        for d in [
            self.needs_action, self.pending_approval, self.approved,
            self.rejected, self.done, self.plans, self.inbox, self.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Initialize skill registry
        vault_paths = {
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

        self.registry = SkillRegistry(vault_paths)
        self._register_all_skills()

        self.processed_files = set()
        self.running = False

    def _register_all_skills(self):
        """Register all available agent skills."""
        skills = [
            ClassifySkill, MoveToeDoneSkill, UpdateDashboardSkill,
            TaskPlannerSkill, VaultFileManagerSkill, VaultWatcherSkill,
            HumanApprovalSkill, GmailSendSkill, LinkedInPostSkill,
            PlanCreatorSkill, ApprovalWatcherSkill, SchedulerSkill,
            CEOBriefingSkill, LinkedInAutoPostSkill, AuditLogSkill,
        ]
        for skill in skills:
            self.registry.register(skill)

    def log_entry(self, message: str):
        """Write to system logs."""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
        line = f"| {timestamp} | {message} |\n"
        with open(self.system_logs, "a", encoding="utf-8") as f:
            f.write(line)
        logger.info(message)

    def process_needs_action(self):
        """Process files in Needs_Action/ — classify, plan, and route."""
        for f in self.needs_action.iterdir():
            if not f.is_file() or f.name in self.processed_files:
                continue

            self.log_entry(f"Processing: {f.name}")
            self.processed_files.add(f.name)

            # Step 1: Classify
            result = self.registry.run("classify", f)

            # Step 2: Create a plan
            self.registry.run("plan_creator", f)

            # Step 3: Determine if approval is needed
            content = ""
            for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
                try:
                    content = f.read_text(encoding=enc).lower()
                    break
                except (UnicodeDecodeError, ValueError):
                    continue

            needs_approval = any(
                kw in content
                for kw in ["payment", "invoice", "send email", "post to linkedin", "delete", "urgent"]
            )

            if needs_approval:
                # Route to approval workflow
                self.registry.run("human_approval", f)
                self.log_entry(f"Routed to approval: {f.name}")
            else:
                # Auto-process and move to done
                self.registry.run("move_to_done", f)
                self.log_entry(f"Auto-completed: {f.name}")

    def process_approved(self):
        """Execute approved actions from the Approved/ folder."""
        for f in self.approved.iterdir():
            if not f.is_file():
                continue

            self.log_entry(f"Executing approved action: {f.name}")

            content = ""
            for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
                try:
                    content = f.read_text(encoding=enc).lower()
                    break
                except (UnicodeDecodeError, ValueError):
                    continue

            # Execute based on action type
            if "linkedin" in content or "linkedin" in f.name.lower():
                self.registry.run("linkedin_auto_post", f)
            elif "email" in content or "email" in f.name.lower():
                self.registry.run("gmail_send", f)

            # Log the action
            self.registry.run("audit_log", f)

            # Move to Done
            dest = self.done / f.name
            if dest.exists():
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                dest = self.done / f"{f.stem}_{ts}{f.suffix}"
            shutil.move(str(f), str(dest))
            self.log_entry(f"Approved action completed: {f.name}")

    def process_rejected(self):
        """Archive rejected actions."""
        for f in self.rejected.iterdir():
            if not f.is_file():
                continue

            self.log_entry(f"Action rejected: {f.name}")
            self.registry.run("audit_log", f)

            # Move to Done with rejected prefix
            dest = self.done / f"REJECTED_{f.name}"
            if dest.exists():
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                dest = self.done / f"REJECTED_{f.stem}_{ts}{f.suffix}"
            shutil.move(str(f), str(dest))

    def run_cycle(self):
        """Run one orchestration cycle."""
        self.process_needs_action()
        self.process_approved()
        self.process_rejected()
        self.registry.run("update_dashboard")

    def run(self, interval: int = 10):
        """Main orchestration loop."""
        self.running = True
        self.log_entry("Orchestrator started")

        print("=" * 50)
        print("  AI Employee — Orchestrator")
        print(f"  Vault: {self.vault_path}")
        print(f"  Skills: {self.registry.list_skills()}")
        print(f"  Cycle interval: {interval}s")
        print("=" * 50)

        try:
            while self.running:
                self.run_cycle()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.running = False
            self.log_entry("Orchestrator stopped by user")


def main():
    parser = argparse.ArgumentParser(description="AI Employee Orchestrator")
    parser.add_argument(
        "--vault-path",
        default=str(Path(__file__).parent / "AI_Employee_Vault"),
        help="Path to the Obsidian vault",
    )
    parser.add_argument("--interval", type=int, default=10, help="Cycle interval in seconds")
    args = parser.parse_args()

    orchestrator = Orchestrator(args.vault_path)
    orchestrator.run(args.interval)


if __name__ == "__main__":
    main()
