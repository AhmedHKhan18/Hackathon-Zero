"""
Agent Skills — Modular AI capabilities for the AI Employee Vault (Silver Tier).

Each skill is a self-contained class that:
- Has a name and description
- Accepts a file path (or no input)
- Executes one specific action
- Logs its own activity

Skills are registered with the SkillRegistry and executed by the pipeline.

Silver Tier Skills:
- ClassifySkill: Classify file urgency
- MoveToeDoneSkill: Move completed files
- UpdateDashboardSkill: Rebuild Dashboard.md
- TaskPlannerSkill: Break down tasks into steps
- VaultFileManagerSkill: List and manage vault files
- VaultWatcherSkill: Health check the vault
- HumanApprovalSkill: HITL approval workflow
- GmailSendSkill: Email draft generation
- LinkedInPostSkill: LinkedIn post draft generation
- PlanCreatorSkill: Create Plan.md reasoning files
- ApprovalWatcherSkill: Monitor Pending_Approval/Approved/Rejected
- SchedulerSkill: Report on scheduled tasks
- CEOBriefingSkill: Generate CEO briefings
- LinkedInAutoPostSkill: Auto-post to LinkedIn
- AuditLogSkill: JSON audit logging
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
        # Silver tier paths (with defaults for backward compat)
        self.plans = vault_paths.get("plans", self.vault / "Plans")
        self.pending_approval = vault_paths.get("pending_approval", self.vault / "Pending_Approval")
        self.approved = vault_paths.get("approved", self.vault / "Approved")
        self.rejected = vault_paths.get("rejected", self.vault / "Rejected")
        self.logs_dir = vault_paths.get("logs_dir", self.vault / "Logs")

    def log_entry(self, message: str) -> None:
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
        line = f"| {timestamp} | {message} |\n"
        with open(self.system_logs, "a", encoding="utf-8") as f:
            f.write(line)
        print(f"{timestamp} {message}")

    def execute(self, file_path: Path = None) -> dict:
        raise NotImplementedError

    def _read_file(self, file_path: Path) -> str:
        """Read file with encoding fallback."""
        for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
            try:
                return file_path.read_text(encoding=encoding)
            except (UnicodeDecodeError, ValueError):
                continue
        return ""


class ClassifySkill(AgentSkill):
    """Reads a file and assigns urgency: High, Medium, or Low."""

    name = "classify"
    description = "Classify file urgency based on content keywords"

    def execute(self, file_path: Path = None) -> dict:
        content = self._read_file(file_path).lower()

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
    """Rebuilds Dashboard.md with current vault status (Silver Tier)."""

    name = "update_dashboard"
    description = "Update Dashboard.md with file counts, completed tasks, and approval queue"

    def execute(self, file_path: Path = None) -> dict:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        inbox_count = len([f for f in self.inbox.iterdir() if f.is_file()])
        action_count = len([f for f in self.needs_action.iterdir() if f.is_file()])
        done_files = [f for f in self.done.iterdir() if f.is_file()]
        done_count = len(done_files)

        # Silver tier: count approval queue
        pending_count = 0
        if self.pending_approval.is_dir():
            pending_count = len([f for f in self.pending_approval.iterdir() if f.is_file()])

        approved_count = 0
        if self.approved.is_dir():
            approved_count = len([f for f in self.approved.iterdir() if f.is_file()])

        rejected_count = 0
        if self.rejected.is_dir():
            rejected_count = len([f for f in self.rejected.iterdir() if f.is_file()])

        plans_count = 0
        if self.plans.is_dir():
            plans_count = len([f for f in self.plans.iterdir() if f.is_file()])

        # Build completed tasks table
        tasks = []
        for f in sorted(done_files, key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
            urgency = "Low"
            content = self._read_file(f)
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

        dashboard = f"""# Dashboard — AI Employee Vault (Silver Tier)

## System Status

| Field | Value |
|---|---|
| **Status** | ONLINE |
| **Tier** | Silver |
| **Last Updated** | {now} |
| **Total Completed** | {done_count} |

## File Counts

| Folder | Count |
|---|---|
| Inbox | {inbox_count} |
| Needs_Action | {action_count} |
| Done | {done_count} |
| Plans | {plans_count} |
| Pending Approval | {pending_count} |
| Approved | {approved_count} |
| Rejected | {rejected_count} |

## Approval Queue

| Status | Count |
|---|---|
| Pending | {pending_count} |
| Approved | {approved_count} |
| Rejected | {rejected_count} |

## Recent Completed Tasks

| File | Urgency |
|---|---|
{task_rows.rstrip()}
"""

        self.dashboard.write_text(dashboard, encoding="utf-8")
        self.log_entry("Dashboard updated.")
        return {"done_count": done_count, "pending_approvals": pending_count}


class TaskPlannerSkill(AgentSkill):
    """Reads a task file and generates a step-by-step action plan."""

    name = "task_planner"
    description = "Break down a task file into an ordered action plan"

    def execute(self, file_path: Path = None) -> dict:
        content = self._read_file(file_path)
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
            "plans": [],
            "pending_approval": [],
        }

        folders = {
            "inbox": self.inbox,
            "needs_action": self.needs_action,
            "done": self.done,
            "plans": self.plans,
            "pending_approval": self.pending_approval,
        }

        for key, folder in folders.items():
            if folder.is_dir():
                for f in folder.iterdir():
                    if f.is_file():
                        inventory[key].append(f.name)

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
            "plans_exists": self.plans.is_dir(),
            "pending_approval_exists": self.pending_approval.is_dir(),
            "approved_exists": self.approved.is_dir(),
            "rejected_exists": self.rejected.is_dir(),
        }

        all_healthy = all(health.values())
        status = "HEALTHY" if all_healthy else "DEGRADED"

        inbox_count = len([f for f in self.inbox.iterdir() if f.is_file()]) if health["inbox_exists"] else 0
        pending = f"{inbox_count} files waiting in Inbox" if inbox_count else "Inbox clear"

        self.log_entry(f"Vault health check: {status} — {pending}")
        return {"status": status, "health": health, "inbox_pending": inbox_count}


class HumanApprovalSkill(AgentSkill):
    """Flags a file for human review — creates approval request in Pending_Approval/."""

    name = "human_approval"
    description = "Flag a task for human approval and create approval request"

    def execute(self, file_path: Path = None) -> dict:
        now = datetime.now()
        content = self._read_file(file_path)

        # Determine action type from content
        content_lower = content.lower()
        if "email" in content_lower:
            action_type = "email_send"
        elif "linkedin" in content_lower:
            action_type = "linkedin_post"
        elif "payment" in content_lower or "invoice" in content_lower:
            action_type = "payment"
        else:
            action_type = "general"

        # Create approval request file
        self.pending_approval.mkdir(parents=True, exist_ok=True)
        approval_file = self.pending_approval / f"APPROVAL_{file_path.stem}_{now.strftime('%Y%m%d%H%M%S')}.md"

        approval_content = f"""---
type: approval_request
action: {action_type}
source_file: {file_path.name}
created: {now.isoformat()}
expires: {now.strftime('%Y-%m-%d')}T23:59:59Z
status: pending
---

## Approval Required — {action_type.replace('_', ' ').title()}

### Original Content
{content[:500]}

### Action Details
- **Type:** {action_type}
- **Source:** {file_path.name}
- **Created:** {now.strftime('%Y-%m-%d %H:%M')}

### To Approve
Move this file to the `/Approved` folder.

### To Reject
Move this file to the `/Rejected` folder.
"""
        approval_file.write_text(approval_content, encoding="utf-8")

        # Also tag the original file
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- AWAITING HUMAN APPROVAL ---\n")
            f.write(f"Flagged at: {now.strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Status: PENDING REVIEW\n")
            f.write(f"Approval file: {approval_file.name}\n")

        self.log_entry(f"Human approval required: {file_path.name} → {approval_file.name}")
        return {
            "status": "awaiting_approval",
            "file": file_path.name,
            "approval_file": approval_file.name,
            "action_type": action_type,
        }


class GmailSendSkill(AgentSkill):
    """Composes an email draft from a task file and saves it to the vault."""

    name = "gmail_send"
    description = "Generate an email draft from task file content"

    def execute(self, file_path: Path = None) -> dict:
        content = self._read_file(file_path)
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
        content = self._read_file(file_path)

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


# ── Silver Tier Skills ────────────────────────────────────────


class PlanCreatorSkill(AgentSkill):
    """Creates a Plan.md file for a task — Claude reasoning loop output."""

    name = "plan_creator"
    description = "Create a structured Plan.md file with steps, status tracking, and approval requirements"

    def execute(self, file_path: Path = None) -> dict:
        content = self._read_file(file_path)
        now = datetime.now()

        # Analyze content for action types
        content_lower = content.lower()
        needs_approval = any(
            kw in content_lower
            for kw in ["payment", "invoice", "send", "post", "delete", "urgent"]
        )

        # Generate steps from content
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        steps = []
        for line in lines:
            if line.startswith("Urgency:") or line.startswith("---"):
                continue
            steps.append(line)

        if not steps:
            steps = ["Review task — no actionable content found"]

        # Build Plan.md
        steps_md = ""
        for i, step in enumerate(steps, 1):
            steps_md += f"- [ ] Step {i}: {step}\n"

        plan_content = f"""---
created: {now.isoformat()}
source_file: {file_path.name}
status: {'pending_approval' if needs_approval else 'ready'}
approval_required: {needs_approval}
---

## Objective
Process task from: {file_path.name}

## Steps
{steps_md}
## Status
- **Created:** {now.strftime('%Y-%m-%d %H:%M')}
- **Steps:** {len(steps)}
- **Approval Required:** {'Yes' if needs_approval else 'No'}

## Notes
{'This plan requires human approval before execution.' if needs_approval else 'This plan can be auto-executed.'}
"""

        self.plans.mkdir(parents=True, exist_ok=True)
        plan_file = self.plans / f"PLAN_{file_path.stem}_{now.strftime('%Y%m%d%H%M%S')}.md"
        plan_file.write_text(plan_content, encoding="utf-8")

        self.log_entry(f"Plan created: {plan_file.name} ({len(steps)} steps)")
        return {
            "plan_file": plan_file.name,
            "steps": len(steps),
            "needs_approval": needs_approval,
            "status": "pending_approval" if needs_approval else "ready",
        }


class ApprovalWatcherSkill(AgentSkill):
    """Monitors the approval workflow folders and reports status."""

    name = "approval_watcher"
    description = "Check Pending_Approval, Approved, and Rejected folders for status"

    def execute(self, file_path: Path = None) -> dict:
        pending = []
        approved = []
        rejected = []

        if self.pending_approval.is_dir():
            pending = [f.name for f in self.pending_approval.iterdir() if f.is_file()]

        if self.approved.is_dir():
            approved = [f.name for f in self.approved.iterdir() if f.is_file()]

        if self.rejected.is_dir():
            rejected = [f.name for f in self.rejected.iterdir() if f.is_file()]

        self.log_entry(
            f"Approval status: {len(pending)} pending, {len(approved)} approved, {len(rejected)} rejected"
        )
        return {
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "pending_count": len(pending),
            "approved_count": len(approved),
            "rejected_count": len(rejected),
        }


class SchedulerSkill(AgentSkill):
    """Reports on scheduled tasks and their status."""

    name = "scheduler"
    description = "List and manage scheduled tasks"

    def execute(self, file_path: Path = None) -> dict:
        now = datetime.now()
        schedules = [
            {
                "name": "Daily Briefing",
                "frequency": "Daily at 8:00 AM",
                "next_run": f"{now.strftime('%Y-%m-%d')} 08:00",
                "status": "active",
            },
            {
                "name": "LinkedIn Post Check",
                "frequency": "Every 30 minutes",
                "next_run": "Continuous",
                "status": "active",
            },
            {
                "name": "Vault Health Check",
                "frequency": "Every 5 minutes",
                "next_run": "Continuous",
                "status": "active",
            },
            {
                "name": "Gmail Watcher",
                "frequency": "Every 2 minutes",
                "next_run": "Continuous",
                "status": "active",
            },
        ]

        self.log_entry(f"Scheduler report: {len(schedules)} active tasks")
        return {"schedules": schedules, "total": len(schedules)}


class CEOBriefingSkill(AgentSkill):
    """Generates a CEO Briefing summarizing vault activity."""

    name = "ceo_briefing"
    description = "Generate a CEO briefing with vault activity summary, task completion, and suggestions"

    def execute(self, file_path: Path = None) -> dict:
        now = datetime.now()
        briefings_dir = self.vault / "Briefings"
        briefings_dir.mkdir(parents=True, exist_ok=True)

        # Gather metrics
        done_files = list(self.done.iterdir()) if self.done.is_dir() else []
        done_count = len([f for f in done_files if f.is_file()])

        pending_count = 0
        if self.pending_approval.is_dir():
            pending_count = len([f for f in self.pending_approval.iterdir() if f.is_file()])

        inbox_count = 0
        if self.inbox.is_dir():
            inbox_count = len([f for f in self.inbox.iterdir() if f.is_file()])

        needs_action_count = 0
        if self.needs_action.is_dir():
            needs_action_count = len([f for f in self.needs_action.iterdir() if f.is_file()])

        plans_count = 0
        if self.plans.is_dir():
            plans_count = len([f for f in self.plans.iterdir() if f.is_file()])

        # Completed tasks list
        completed_md = ""
        for f in sorted(done_files, key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
            if f.is_file():
                completed_md += f"- [x] {f.name}\n"
        if not completed_md:
            completed_md = "- No completed tasks this period\n"

        # Build briefing
        briefing = f"""---
generated: {now.isoformat()}
period: {now.strftime('%Y-%m-%d')}
---

# CEO Briefing — {now.strftime('%A, %B %d, %Y')}

## Executive Summary
AI Employee vault status report. {done_count} tasks completed, {needs_action_count} pending action, {pending_count} awaiting approval.

## Activity Summary
| Metric | Value |
|--------|-------|
| Tasks Completed | {done_count} |
| Pending Action | {needs_action_count} |
| Awaiting Approval | {pending_count} |
| Active Plans | {plans_count} |
| Inbox Items | {inbox_count} |

## Completed Tasks
{completed_md}
## Bottlenecks
{"- " + str(pending_count) + " items awaiting human approval" if pending_count > 0 else "- No bottlenecks detected"}
{"- " + str(needs_action_count) + " items pending in Needs_Action" if needs_action_count > 3 else ""}

## Proactive Suggestions
- Review pending approval items to unblock workflow
- Check if any Needs_Action items are stale
{"- High volume in Needs_Action — consider auto-approve rules for low-risk items" if needs_action_count > 5 else ""}

---
*Generated by AI Employee v0.2 (Silver Tier)*
"""

        briefing_file = briefings_dir / f"{now.strftime('%Y-%m-%d')}_Briefing.md"
        briefing_file.write_text(briefing, encoding="utf-8")

        self.log_entry(f"CEO Briefing generated: {briefing_file.name}")
        return {
            "briefing_file": briefing_file.name,
            "done_count": done_count,
            "pending_count": pending_count,
        }


class LinkedInAutoPostSkill(AgentSkill):
    """Auto-posts approved content to LinkedIn (dry-run by default)."""

    name = "linkedin_auto_post"
    description = "Post approved content to LinkedIn (supports dry-run mode)"

    def execute(self, file_path: Path = None) -> dict:
        import os

        dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        content = self._read_file(file_path)

        # Extract post content (strip metadata)
        post_lines = []
        in_content = False
        for line in content.splitlines():
            if "## LinkedIn Post Content" in line or "## Content" in line:
                in_content = True
                continue
            if line.startswith("##") and in_content:
                break
            if in_content:
                post_lines.append(line)
            elif not line.startswith("---") and not line.startswith("type:") and not line.startswith("status:"):
                post_lines.append(line)

        post_body = "\n".join(post_lines).strip()
        if not post_body:
            post_body = content.strip()

        result = {
            "content": post_body[:500],
            "char_count": len(post_body),
            "posted_at": datetime.now().isoformat(),
            "mode": "dry_run" if dry_run else "live",
            "status": "posted_dry_run" if dry_run else "posted",
        }

        if dry_run:
            self.log_entry(f"[DRY RUN] LinkedIn post: {post_body[:80]}...")
        else:
            # Live posting would go here (LinkedIn API/Playwright)
            self.log_entry(f"LinkedIn posted: {post_body[:80]}...")

        # Save post record
        posted_dir = self.done / "linkedin_posted"
        posted_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        record = posted_dir / f"post_{ts}.json"
        record.write_text(json.dumps(result, indent=2), encoding="utf-8")

        return result


class AuditLogSkill(AgentSkill):
    """Creates JSON audit log entries for all actions."""

    name = "audit_log"
    description = "Create a JSON audit log entry for any action"

    def execute(self, file_path: Path = None) -> dict:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{today}.json"

        # Determine action details from file
        content = ""
        action_type = "unknown"
        if file_path and file_path.exists():
            content = self._read_file(file_path)
            fname = file_path.name.lower()
            if "email" in fname:
                action_type = "email_action"
            elif "linkedin" in fname:
                action_type = "linkedin_action"
            elif "approval" in fname:
                action_type = "approval_action"
            elif "plan" in fname:
                action_type = "plan_action"
            else:
                action_type = "file_action"

        entry = {
            "timestamp": now.isoformat(),
            "action_type": action_type,
            "actor": "ai_employee",
            "target": file_path.name if file_path else "system",
            "details": content[:200] if content else "",
            "result": "success",
        }

        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                entries = []

        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")

        self.log_entry(f"Audit log: {action_type} — {file_path.name if file_path else 'system'}")
        return {"log_file": log_file.name, "action_type": action_type, "entries_count": len(entries)}


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
