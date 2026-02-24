"""
Orchestrator — Master process for the AI Employee (Gold Tier).

Manages all watchers, monitors folders, handles approval workflows,
coordinates the reasoning loop, executes Ralph Wiggum autonomous plans,
handles cross-domain workflows, and manages error recovery.

Usage:
    python orchestrator.py [--vault-path PATH]

Features:
    - Starts and monitors all watcher processes
    - Watches Approved/ folder to execute approved actions
    - Watches Needs_Action/ for new tasks requiring plans
    - Executes Ralph Wiggum autonomous loop for active plans
    - Coordinates cross-domain workflows (accounting + social + email)
    - Error recovery with retry handler
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
    WhatsAppReplySkill,
    PlanCreatorSkill,
    ApprovalWatcherSkill,
    SchedulerSkill,
    CEOBriefingSkill,
    LinkedInAutoPostSkill,
    AuditLogSkill,
    OdooAccountingSkill,
    FacebookPostSkill,
    InstagramPostSkill,
    TwitterPostSkill,
    SocialMediaSummarySkill,
    WeeklyBusinessAuditSkill,
    ErrorRecoverySkill,
)
from retry_handler import RetryHandler
from ralph_loop import RalphWiggumLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """Master process that coordinates all AI Employee components (Gold Tier)."""

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
            self.vault_path / "In_Progress",
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

        # Gold tier: retry handler and Ralph loop
        self.retry_handler = RetryHandler(vault_path=self.vault_path)
        self.ralph_loop = RalphWiggumLoop(
            vault_path=self.vault_path,
            registry=self.registry,
        )

        self.processed_files = set()
        self.running = False

    def _register_all_skills(self):
        """Register all 23 agent skills."""
        skills = [
            # Bronze tier
            ClassifySkill, MoveToeDoneSkill, UpdateDashboardSkill,
            TaskPlannerSkill, VaultFileManagerSkill, VaultWatcherSkill,
            HumanApprovalSkill, GmailSendSkill, LinkedInPostSkill,
            # Silver tier
            WhatsAppReplySkill, PlanCreatorSkill, ApprovalWatcherSkill,
            SchedulerSkill, CEOBriefingSkill, LinkedInAutoPostSkill,
            AuditLogSkill,
            # Gold tier
            OdooAccountingSkill, FacebookPostSkill, InstagramPostSkill,
            TwitterPostSkill, SocialMediaSummarySkill,
            WeeklyBusinessAuditSkill, ErrorRecoverySkill,
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

            try:
                # Step 1: Classify
                result = self.retry_handler.execute_with_retry(
                    self.registry.run, "classify", f, service_name="classify"
                )

                # Step 2: Create a plan
                self.retry_handler.execute_with_retry(
                    self.registry.run, "plan_creator", f, service_name="plan_creator"
                )

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
                    self.registry.run("human_approval", f)
                    self.log_entry(f"Routed to approval: {f.name}")
                else:
                    self.registry.run("move_to_done", f)
                    self.log_entry(f"Auto-completed: {f.name}")
            except Exception as e:
                self.retry_handler.log_error("process_needs_action", e, {"file": f.name})
                self.log_entry(f"Error processing {f.name}: {e}")

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
            if "whatsapp" in content or "whatsapp" in f.name.lower():
                self.registry.run("whatsapp_reply", f)
            elif "linkedin" in content or "linkedin" in f.name.lower():
                self.registry.run("linkedin_auto_post", f)
            elif "email" in content or "email" in f.name.lower():
                self.registry.run("gmail_send", f)
            elif "facebook" in content or "facebook" in f.name.lower():
                self.registry.run("facebook_post", f)
            elif "instagram" in content or "instagram" in f.name.lower():
                self.registry.run("instagram_post", f)
            elif "twitter" in content or "tweet" in f.name.lower():
                self.registry.run("twitter_post", f)

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

    def execute_ralph_loop(self):
        """Execute the Ralph Wiggum autonomous loop for active plans."""
        try:
            result = self.ralph_loop.run()
            if result["plans_processed"] > 0:
                self.log_entry(
                    f"Ralph loop: {result['plans_processed']} plans, "
                    f"{result['total_steps_completed']} steps completed"
                )
            return result
        except Exception as e:
            self.retry_handler.log_error("ralph_loop", e)
            self.log_entry(f"Ralph loop error: {e}")
            return {"status": "error", "error": str(e)}

    def process_cross_domain_tasks(self):
        """Coordinate and execute multi-domain workflows (e.g., invoice → email → social)."""
        for f in self.needs_action.iterdir():
            if not f.is_file() or f.name in self.processed_files:
                continue

            content = ""
            for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
                try:
                    content = f.read_text(encoding=enc).lower()
                    break
                except (UnicodeDecodeError, ValueError):
                    continue

            # Detect cross-domain tasks
            domains = []
            if any(kw in content for kw in ["invoice", "payment", "accounting", "balance", "profit"]):
                domains.append("accounting")
            if any(kw in content for kw in ["email", "send email", "gmail"]):
                domains.append("email")
            if any(kw in content for kw in ["facebook", "instagram", "twitter", "social", "post"]):
                domains.append("social_media")

            if len(domains) > 1:
                workflow_id = f"WF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                self.log_entry(f"Cross-domain workflow {workflow_id}: {domains}")
                audit_skill = self.registry.get("audit_log")
                audit_skill.log_cross_domain_workflow(workflow_id, domains, "started")

                # Execute each domain's skills in dependency order
                results = {}
                failed = False

                # 1. Accounting first (other domains may depend on financial data)
                if "accounting" in domains:
                    try:
                        result = self.retry_handler.execute_with_retry(
                            self.registry.run, "odoo_accounting", f, service_name="odoo"
                        )
                        results["accounting"] = result
                        self.log_entry(f"  [{workflow_id}] Accounting: {result.get('action', 'done')}")
                    except Exception as e:
                        self.retry_handler.log_error("cross_domain_accounting", e, {"workflow": workflow_id})
                        results["accounting"] = {"status": "error", "error": str(e)}
                        failed = True

                # 2. Email (may reference accounting results)
                if "email" in domains and not failed:
                    try:
                        result = self.retry_handler.execute_with_retry(
                            self.registry.run, "gmail_send", f, service_name="gmail"
                        )
                        results["email"] = result
                        self.log_entry(f"  [{workflow_id}] Email: sent")
                    except Exception as e:
                        self.retry_handler.log_error("cross_domain_email", e, {"workflow": workflow_id})
                        results["email"] = {"status": "error", "error": str(e)}
                        failed = True

                # 3. Social media last (broadcast after internal actions done)
                if "social_media" in domains and not failed:
                    social_skills = []
                    if "facebook" in content:
                        social_skills.append("facebook_post")
                    if "instagram" in content:
                        social_skills.append("instagram_post")
                    if "twitter" in content or "tweet" in content:
                        social_skills.append("twitter_post")
                    # Default: post to all if just "social" or "post" mentioned
                    if not social_skills:
                        social_skills.append("facebook_post")

                    for skill_name in social_skills:
                        try:
                            result = self.retry_handler.execute_with_retry(
                                self.registry.run, skill_name, f, service_name=skill_name
                            )
                            results[skill_name] = result
                            self.log_entry(f"  [{workflow_id}] {skill_name}: posted")
                        except Exception as e:
                            self.retry_handler.log_error(f"cross_domain_{skill_name}", e, {"workflow": workflow_id})
                            results[skill_name] = {"status": "error", "error": str(e)}

                # Mark file as processed and log final status
                self.processed_files.add(f.name)
                final_status = "completed" if not failed else "partial"
                audit_skill.log_cross_domain_workflow(workflow_id, domains, final_status)
                self.log_entry(f"Cross-domain workflow {workflow_id}: {final_status} ({len(results)} actions)")

                # Move to Done
                dest = self.done / f.name
                if dest.exists():
                    ts = datetime.now().strftime("%Y%m%d%H%M%S")
                    dest = self.done / f"{f.stem}_{ts}{f.suffix}"
                shutil.move(str(f), str(dest))

    def check_error_recovery(self):
        """Retry failed items from error queue."""
        try:
            result = self.registry.run("error_recovery")
            if result.get("errors_found", 0) > 0:
                self.log_entry(
                    f"Error recovery: {result['recovered']} recovered, "
                    f"{result['failed']} need review"
                )
            return result
        except Exception as e:
            self.log_entry(f"Error recovery check failed: {e}")
            return {"status": "error", "error": str(e)}

    def run_cycle(self):
        """Run one orchestration cycle (Gold Tier)."""
        self.process_needs_action()
        self.process_approved()
        self.process_rejected()
        self.process_cross_domain_tasks()
        self.execute_ralph_loop()
        self.check_error_recovery()
        self.registry.run("update_dashboard")

    def run(self, interval: int = 10):
        """Main orchestration loop."""
        self.running = True
        self.log_entry("Gold Tier Orchestrator started")

        skills = self.registry.list_skills()
        print("=" * 55)
        print("  AI Employee — Gold Tier Orchestrator")
        print(f"  Vault: {self.vault_path}")
        print(f"  Skills ({len(skills)}): {skills}")
        print(f"  Cycle interval: {interval}s")
        print(f"  Ralph Loop: enabled (max {self.ralph_loop.max_iterations} iterations)")
        print(f"  Error Recovery: enabled")
        print("=" * 55)

        try:
            while self.running:
                self.run_cycle()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.running = False
            self.log_entry("Orchestrator stopped by user")


def main():
    parser = argparse.ArgumentParser(description="AI Employee Orchestrator (Gold Tier)")
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
