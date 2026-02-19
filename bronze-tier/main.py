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
)

VAULT = Path(__file__).parent / "AI_Employee_Vault"
INBOX = VAULT / "Inbox"
NEEDS_ACTION = VAULT / "Needs_Action"
DONE = VAULT / "Done"
SYSTEM_LOGS = VAULT / "System_Logs.md"
DASHBOARD = VAULT / "Dashboard.md"

VAULT_PATHS = {
    "vault": VAULT,
    "inbox": INBOX,
    "needs_action": NEEDS_ACTION,
    "done": DONE,
    "system_logs": SYSTEM_LOGS,
    "dashboard": DASHBOARD,
}

# Initialize skill registry
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
        registry.run("move_to_done", dest)
        registry.run("update_dashboard")


def main():
    print("=" * 50)
    print("  AI Employee Vault — Inbox Watcher")
    print("=" * 50)
    print(f"  Watching: {INBOX}")
    print(f"  Move to:  {NEEDS_ACTION}")
    print(f"  Logs:     {SYSTEM_LOGS}")
    print("=" * 50)
    print(f"  Skills:   {registry.list_skills()}")
    print("  Drop files into Inbox/ to trigger processing.")
    print("  Press Ctrl+C to stop.\n")

    log_entry("Watcher started. Monitoring Inbox folder.")

    observer = Observer()
    observer.schedule(InboxHandler(), str(INBOX), recursive=False)
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
