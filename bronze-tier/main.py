import time
import shutil
from pathlib import Path
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

VAULT = Path(__file__).parent / "AI_Employee_Vault"
INBOX = VAULT / "Inbox"
NEEDS_ACTION = VAULT / "Needs_Action"
DONE = VAULT / "Done"
SYSTEM_LOGS = VAULT / "System_Logs.md"
DASHBOARD = VAULT / "Dashboard.md"


def log_entry(message: str) -> None:
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
    line = f"| {timestamp} | {message} |\n"
    with open(SYSTEM_LOGS, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"{timestamp} {message}")


def classify_task(file_path: Path) -> str:
    content = ""
    for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
        try:
            content = file_path.read_text(encoding=encoding).lower()
            break
        except (UnicodeDecodeError, ValueError):
            continue

    if "urgent" in content:
        urgency = "High"
    elif "soon" in content:
        urgency = "Medium"
    else:
        urgency = "Low"

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(f"\nUrgency: {urgency}\n")

    log_entry(f"Classified: {file_path.name} → Urgency: {urgency}")
    return urgency


def update_dashboard() -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    inbox_count = len([f for f in INBOX.iterdir() if f.is_file()])
    action_count = len([f for f in NEEDS_ACTION.iterdir() if f.is_file()])
    done_files = [f for f in DONE.iterdir() if f.is_file()]
    done_count = len(done_files)

    # Read urgency from each completed file
    tasks = []
    for f in sorted(done_files, key=lambda x: x.stat().st_mtime):
        urgency = "Low"
        content = ""
        for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
            try:
                content = f.read_text(encoding=encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        for line in content.splitlines():
            if line.startswith("Urgency:"):
                urgency = line.split(":", 1)[1].strip()
                break
        tasks.append((f.name, urgency))

    # Build completed tasks table
    task_rows = ""
    for name, urgency in tasks:
        task_rows += f"| {name} | {urgency} |\n"
    if not task_rows:
        task_rows = "| — | — |\n"

    dashboard = f"""# Dashboard — AI Employee Vault

## System Status

| Field | Value |
|---|---|
| **Status** | ONLINE |
| **Last Updated** | {now} |
| **Total Completed** | {done_count} |

## File Counts

| Folder | Count |
|---|---|
| Inbox | {inbox_count} |
| Needs_Action | {action_count} |
| Done | {done_count} |

## Completed Tasks

| File | Urgency |
|---|---|
{task_rows.rstrip()}
"""

    DASHBOARD.write_text(dashboard, encoding="utf-8")
    log_entry("Dashboard updated.")


def move_to_done(file_path: Path) -> None:
    dest = DONE / file_path.name

    if dest.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        dest = DONE / f"{stem}_{ts}{suffix}"

    shutil.move(str(file_path), str(dest))
    log_entry(f"Task completed: {file_path.name}")
    update_dashboard()


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

        classify_task(dest)
        move_to_done(dest)


def main():
    print("=" * 50)
    print("  AI Employee Vault — Inbox Watcher")
    print("=" * 50)
    print(f"  Watching: {INBOX}")
    print(f"  Move to:  {NEEDS_ACTION}")
    print(f"  Logs:     {SYSTEM_LOGS}")
    print("=" * 50)
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
