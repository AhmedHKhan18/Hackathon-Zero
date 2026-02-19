"""
AI Employee Vault — Silver Tier Main Entry Point.

Watches the Inbox folder for new files, processes them through the
agent skills pipeline, and manages the complete workflow including
classification, planning, approval routing, and dashboard updates.

Usage:
    python main.py

For the full orchestrator (with all watchers and scheduling):
    python orchestrator.py
"""

import time
import shutil
from pathlib import Path
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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

VAULT = Path(__file__).parent / "AI_Employee_Vault"
INBOX = VAULT / "Inbox"
NEEDS_ACTION = VAULT / "Needs_Action"
DONE = VAULT / "Done"
PLANS = VAULT / "Plans"
PENDING_APPROVAL = VAULT / "Pending_Approval"
APPROVED = VAULT / "Approved"
REJECTED = VAULT / "Rejected"
LOGS_DIR = VAULT / "Logs"
SYSTEM_LOGS = VAULT / "System_Logs.md"
DASHBOARD = VAULT / "Dashboard.md"

VAULT_PATHS = {
    "vault": VAULT,
    "inbox": INBOX,
    "needs_action": NEEDS_ACTION,
    "done": DONE,
    "system_logs": SYSTEM_LOGS,
    "dashboard": DASHBOARD,
    "plans": PLANS,
    "pending_approval": PENDING_APPROVAL,
    "approved": APPROVED,
    "rejected": REJECTED,
    "logs_dir": LOGS_DIR,
}

# Ensure all directories exist
for d in [INBOX, NEEDS_ACTION, DONE, PLANS, PENDING_APPROVAL, APPROVED, REJECTED, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Initialize skill registry with all Silver tier skills
registry = SkillRegistry(VAULT_PATHS)
registry.register(ClassifySkill)
registry.register(MoveToeDoneSkill)
registry.register(UpdateDashboardSkill)
registry.register(TaskPlannerSkill)
registry.register(VaultFileManagerSkill)
registry.register(VaultWatcherSkill)
registry.register(HumanApprovalSkill)
registry.register(GmailSendSkill)
registry.register(LinkedInPostSkill)
registry.register(PlanCreatorSkill)
registry.register(ApprovalWatcherSkill)
registry.register(SchedulerSkill)
registry.register(CEOBriefingSkill)
registry.register(LinkedInAutoPostSkill)
registry.register(AuditLogSkill)


def log_entry(message: str) -> None:
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
    line = f"| {timestamp} | {message} |\n"
    with open(SYSTEM_LOGS, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"{timestamp} {message}")


class InboxHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        src = Path(event.src_path)

        # Small delay to let file finish writing
        time.sleep(0.5)

        if not src.exists():
            return

        dest = NEEDS_ACTION / src.name

        # Avoid duplicates — append timestamp if name already exists
        if dest.exists():
            stem = src.stem
            suffix = src.suffix
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            dest = NEEDS_ACTION / f"{stem}_{ts}{suffix}"

        shutil.move(str(src), str(dest))
        log_entry(f"File detected: {src.name}")

        # Execute agent skills pipeline
        registry.run("classify", dest)

        # Silver tier: Create a plan for each task
        registry.run("plan_creator", dest)

        # Check if task needs approval (sensitive keywords)
        content = ""
        for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
            try:
                content = dest.read_text(encoding=enc).lower()
                break
            except (UnicodeDecodeError, ValueError):
                continue

        needs_approval = any(
            kw in content
            for kw in ["payment", "invoice", "send email", "post to linkedin"]
        )

        if needs_approval:
            registry.run("human_approval", dest)
            log_entry(f"Routed to approval: {dest.name}")
        else:
            registry.run("move_to_done", dest)

        # Log the action
        registry.run("audit_log", dest if dest.exists() else None)
        registry.run("update_dashboard")


class ApprovalHandler(FileSystemEventHandler):
    """Watches the Approved/ folder to execute approved actions."""

    def on_created(self, event):
        if event.is_directory:
            return

        src = Path(event.src_path)
        time.sleep(0.5)

        if not src.exists():
            return

        log_entry(f"Approved action detected: {src.name}")

        content = ""
        for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
            try:
                content = src.read_text(encoding=enc).lower()
                break
            except (UnicodeDecodeError, ValueError):
                continue

        # Execute based on action type
        if "linkedin" in content or "linkedin" in src.name.lower():
            registry.run("linkedin_auto_post", src)
        elif "email" in content or "email" in src.name.lower():
            registry.run("gmail_send", src)

        registry.run("audit_log", src)

        # Move to Done
        dest = DONE / src.name
        if dest.exists():
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            dest = DONE / f"{src.stem}_{ts}{src.suffix}"
        shutil.move(str(src), str(dest))

        registry.run("update_dashboard")
        log_entry(f"Approved action completed: {src.name}")


def main():
    print("=" * 55)
    print("  AI Employee Vault — Silver Tier")
    print("=" * 55)
    print(f"  Watching Inbox:     {INBOX}")
    print(f"  Watching Approved:  {APPROVED}")
    print(f"  Needs Action:       {NEEDS_ACTION}")
    print(f"  Plans:              {PLANS}")
    print(f"  Pending Approval:   {PENDING_APPROVAL}")
    print(f"  Done:               {DONE}")
    print(f"  Logs:               {SYSTEM_LOGS}")
    print("=" * 55)
    print(f"  Skills ({len(registry.list_skills())}): {registry.list_skills()}")
    print("  Drop files into Inbox/ to trigger processing.")
    print("  Move files to Approved/ to execute approved actions.")
    print("  Press Ctrl+C to stop.\n")

    log_entry("Silver Tier Watcher started. Monitoring Inbox and Approved folders.")

    observer = Observer()
    observer.schedule(InboxHandler(), str(INBOX), recursive=False)
    observer.schedule(ApprovalHandler(), str(APPROVED), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        log_entry("Watcher stopped by user.")

    observer.join()


if __name__ == "__main__":
    main()
