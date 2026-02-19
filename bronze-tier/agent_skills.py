"""
Agent Skills — Modular AI capabilities for the AI Employee Vault.

Each skill is a self-contained class that:
- Has a name and description
- Accepts a file path (or no input)
- Executes one specific action
- Logs its own activity

Skills are registered with the SkillRegistry and executed by the pipeline.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime


class AgentSkill:
    """Base class for all agent skills."""

    name: str = ""
    description: str = ""

    def __init__(self, vault_paths: dict):
        self.vault = vault_paths["vault"]
        self.inbox = vault_paths["inbox"]
        self.needs_action = vault_paths["needs_action"]
        self.done = vault_paths["done"]
        self.system_logs = vault_paths["system_logs"]
        self.dashboard = vault_paths["dashboard"]

    def log_entry(self, message: str) -> None:
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
        line = f"| {timestamp} | {message} |\n"
        with open(self.system_logs, "a", encoding="utf-8") as f:
            f.write(line)
        print(f"{timestamp} {message}")

    def execute(self, file_path: Path = None) -> dict:
        raise NotImplementedError


class ClassifySkill(AgentSkill):
    """Reads a file and assigns urgency: High, Medium, or Low."""

    name = "classify"
    description = "Classify file urgency based on content keywords"

    def execute(self, file_path: Path = None) -> dict:
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

        self.log_entry(f"Classified: {file_path.name} → Urgency: {urgency}")
        return {"urgency": urgency}


class MoveToeDoneSkill(AgentSkill):
    """Moves a processed file from Needs_Action to Done."""

    name = "move_to_done"
    description = "Move completed file to Done folder"

    def execute(self, file_path: Path = None) -> dict:
        dest = self.done / file_path.name

        if dest.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            dest = self.done / f"{stem}_{ts}{suffix}"

        shutil.move(str(file_path), str(dest))
        self.log_entry(f"Task completed: {file_path.name}")
        return {"destination": str(dest)}


class UpdateDashboardSkill(AgentSkill):
    """Rebuilds Dashboard.md with current vault status."""

    name = "update_dashboard"
    description = "Update Dashboard.md with file counts and completed tasks"

    def execute(self, file_path: Path = None) -> dict:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        inbox_count = len([f for f in self.inbox.iterdir() if f.is_file()])
        action_count = len([f for f in self.needs_action.iterdir() if f.is_file()])
        done_files = [f for f in self.done.iterdir() if f.is_file()]
        done_count = len(done_files)

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

        self.dashboard.write_text(dashboard, encoding="utf-8")
        self.log_entry("Dashboard updated.")
        return {"done_count": done_count}


class TaskPlannerSkill(AgentSkill):
    """Reads a task file and generates a step-by-step action plan."""

    name = "task_planner"
    description = "Break down a task file into an ordered action plan"

    def execute(self, file_path: Path = None) -> dict:
        content = ""
        for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
            try:
                content = file_path.read_text(encoding=encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue

        lines = [l.strip() for l in content.splitlines() if l.strip()]
        steps = []
        step_num = 1

        for line in lines:
            if line.startswith("Urgency:"):
                continue
            steps.append(f"Step {step_num}: {line}")
            step_num += 1

        if not steps:
            steps.append("Step 1: Review empty task — no content found")

        plan = "\n".join(steps)

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- Action Plan ---\n{plan}\n")

        self.log_entry(f"Task planned: {file_path.name} ({len(steps)} steps)")
        return {"steps": steps, "step_count": len(steps)}


class VaultFileManagerSkill(AgentSkill):
    """Manages files within the vault — list, search, and get info."""

    name = "vault_file_manager"
    description = "List, search, and manage files across vault folders"

    def execute(self, file_path: Path = None) -> dict:
        inventory = {
            "inbox": [],
            "needs_action": [],
            "done": [],
        }

        for f in self.inbox.iterdir():
            if f.is_file():
                inventory["inbox"].append(f.name)
        for f in self.needs_action.iterdir():
            if f.is_file():
                inventory["needs_action"].append(f.name)
        for f in self.done.iterdir():
            if f.is_file():
                inventory["done"].append(f.name)

        total = sum(len(v) for v in inventory.values())
        self.log_entry(f"Vault inventory: {total} files across all folders")
        return {"inventory": inventory, "total_files": total}


class VaultWatcherSkill(AgentSkill):
    """Reports on the current state of the vault watcher system."""

    name = "vault_watcher"
    description = "Check vault watcher status and report folder health"

    def execute(self, file_path: Path = None) -> dict:
        health = {
            "inbox_exists": self.inbox.is_dir(),
            "needs_action_exists": self.needs_action.is_dir(),
            "done_exists": self.done.is_dir(),
            "logs_exists": self.system_logs.is_file(),
            "dashboard_exists": self.dashboard.is_file(),
        }

        all_healthy = all(health.values())
        status = "HEALTHY" if all_healthy else "DEGRADED"

        inbox_count = len([f for f in self.inbox.iterdir() if f.is_file()]) if health["inbox_exists"] else 0
        pending = f"{inbox_count} files waiting in Inbox" if inbox_count else "Inbox clear"

        self.log_entry(f"Vault health check: {status} — {pending}")
        return {"status": status, "health": health, "inbox_pending": inbox_count}


class HumanApprovalSkill(AgentSkill):
    """Flags a file for human review before further processing."""

    name = "human_approval"
    description = "Flag a task for human approval and pause processing"

    def execute(self, file_path: Path = None) -> dict:
        with open(file_path, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            f.write(f"\n--- AWAITING HUMAN APPROVAL ---\n")
            f.write(f"Flagged at: {timestamp}\n")
            f.write(f"Status: PENDING REVIEW\n")

        # Move to Needs_Action if not already there
        if file_path.parent != self.needs_action:
            dest = self.needs_action / file_path.name
            if dest.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                dest = self.needs_action / f"{stem}_{ts}{suffix}"
            shutil.move(str(file_path), str(dest))
            file_path = dest

        self.log_entry(f"Human approval required: {file_path.name}")
        return {"status": "awaiting_approval", "file": file_path.name}


class GmailSendSkill(AgentSkill):
    """Composes an email draft from a task file and saves it to the vault."""

    name = "gmail_send"
    description = "Generate an email draft from task file content"

    def execute(self, file_path: Path = None) -> dict:
        content = ""
        for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
            try:
                content = file_path.read_text(encoding=encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue

        lines = content.splitlines()
        subject = lines[0] if lines else "No Subject"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        draft = {
            "to": "",
            "subject": subject,
            "body": body,
            "status": "draft",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source_file": file_path.name,
        }

        draft_file = self.vault / f"email_draft_{file_path.stem}.json"
        draft_file.write_text(json.dumps(draft, indent=2), encoding="utf-8")

        self.log_entry(f"Email draft created: {draft_file.name} (from {file_path.name})")
        return {"draft_file": draft_file.name, "subject": subject, "status": "draft"}


class LinkedInPostSkill(AgentSkill):
    """Composes a LinkedIn post draft from a task file and saves it to the vault."""

    name = "linkedin_post"
    description = "Generate a LinkedIn post draft from task file content"

    def execute(self, file_path: Path = None) -> dict:
        content = ""
        for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
            try:
                content = file_path.read_text(encoding=encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue

        # Strip internal metadata lines
        post_lines = []
        for line in content.splitlines():
            if line.startswith("Urgency:") or line.startswith("---"):
                continue
            post_lines.append(line)
        post_body = "\n".join(post_lines).strip()

        draft = {
            "content": post_body,
            "status": "draft",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source_file": file_path.name,
            "char_count": len(post_body),
        }

        draft_file = self.vault / f"linkedin_draft_{file_path.stem}.json"
        draft_file.write_text(json.dumps(draft, indent=2), encoding="utf-8")

        self.log_entry(f"LinkedIn draft created: {draft_file.name} ({len(post_body)} chars)")
        return {"draft_file": draft_file.name, "char_count": len(post_body), "status": "draft"}


class SkillRegistry:
    """Registers and manages all available agent skills."""

    def __init__(self, vault_paths: dict):
        self.vault_paths = vault_paths
        self._skills: dict[str, AgentSkill] = {}

    def register(self, skill_class: type) -> None:
        skill = skill_class(self.vault_paths)
        self._skills[skill.name] = skill

    def get(self, name: str) -> AgentSkill:
        return self._skills[name]

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    def run(self, name: str, file_path: Path = None) -> dict:
        skill = self._skills[name]
        return skill.execute(file_path)
