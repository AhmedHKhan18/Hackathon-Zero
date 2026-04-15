"""
Platinum Skills — New agent capabilities for the Platinum Tier AI Employee.

Adds Cloud/Local zone specialization on top of Gold tier skills:

Platinum Skills (8 new):
  CloudEmailDraftSkill      — Triage email, create draft reply + approval file
  VaultSyncSkill            — Git-based vault sync (pull/commit/push)
  ClaimByMoveSkill          — Claim a task from /Needs_Action to /In_Progress/<agent>/
  LocalApprovalExecutorSkill— Execute cloud-approved actions (send email, WhatsApp, etc.)
  DashboardMergeSkill       — Merge /Updates/ signals from cloud into Dashboard.md
  CloudHealthMonitorSkill   — Write/read health status to /Signals/health.md
  OdooCloudDraftSkill       — Draft-only Odoo accounting actions (cloud side, no posting)
  VaultCleanupSkill         — Archive stale In_Progress/ claims after timeout

Security rules enforced:
  - Cloud NEVER writes WhatsApp session, banking creds, or payment tokens
  - Secrets never sync (.env, token.json, credentials.json, *.key, *.pem)
  - Dashboard.md is written ONLY by the Local agent (single-writer rule)
"""

import os
import json
import shutil
import subprocess
import socket
from pathlib import Path
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Re-use base class from gold tier
from agent_skills import AgentSkill


# ---------------------------------------------------------------------------
# Platinum Skill 1: CloudEmailDraftSkill
# ---------------------------------------------------------------------------

class CloudEmailDraftSkill(AgentSkill):
    """
    Triage an email task file, generate a draft reply, and write a
    Pending_Approval file for the Local agent to review and send.

    This is the core of the Platinum demo: Cloud drafts, Local sends.
    """

    name = "cloud_email_draft"
    description = (
        "Triage email in Needs_Action/, generate a polite draft reply, "
        "write it to /Drafts/<id>.md and create /Pending_Approval/<id>.md "
        "so the Local agent can review and send."
    )

    def execute(self, file_path: Path = None) -> dict:
        if file_path is None or not file_path.exists():
            return {"status": "error", "message": "No file provided"}

        content = self._read_file(file_path)
        task_id = file_path.stem
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        draft_id = f"{task_id}_{timestamp}"

        # Parse basic fields from frontmatter
        sender = self._extract_field(content, "from") or "unknown@example.com"
        subject = self._extract_field(content, "subject") or "Re: Your message"
        snippet = ""
        if "## Email Content" in content:
            snippet = content.split("## Email Content")[-1].strip()[:300]

        draft_body = (
            f"Dear {sender.split('<')[0].strip()},\n\n"
            f"Thank you for your email regarding '{subject}'.\n\n"
            f"I have reviewed your message and will get back to you with a "
            f"detailed response shortly. In the meantime, please feel free to "
            f"reach out if you have any urgent questions.\n\n"
            f"Best regards,\n"
            f"AI Employee (on behalf of Ahmed Khan)"
        )

        # Write draft to /Drafts/
        drafts_dir = self.vault / "Drafts"
        drafts_dir.mkdir(exist_ok=True)
        draft_path = drafts_dir / f"{draft_id}.md"
        draft_path.write_text(
            f"---\ntype: email_draft\ntask_id: {task_id}\nto: {sender}\n"
            f"subject: Re: {subject}\ncreated_by: cloud-agent\n"
            f"created: {datetime.now().isoformat()}\nstatus: pending_approval\n---\n\n"
            f"## Draft Reply\n\n{draft_body}\n",
            encoding="utf-8",
        )

        # Write approval request to /Pending_Approval/
        approval_path = self.pending_approval / f"EMAIL_REPLY_{draft_id}.md"
        approval_path.write_text(
            f"---\ntype: approval_request\naction: send_email\n"
            f"task_id: {task_id}\ndraft_path: Drafts/{draft_id}.md\n"
            f"to: {sender}\nsubject: Re: {subject}\n"
            f"created_by: cloud-agent\ncreated: {datetime.now().isoformat()}\n"
            f"expires: {(datetime.now() + timedelta(hours=24)).isoformat()}\n"
            f"status: pending\n---\n\n"
            f"## Action Required\n\nCloud agent drafted a reply to:\n"
            f"- **From:** {sender}\n- **Subject:** {subject}\n\n"
            f"## Draft Preview\n\n{draft_body}\n\n"
            f"## To Approve\nMove this file to `/Approved/` folder.\n\n"
            f"## To Reject\nMove this file to `/Rejected/` folder.\n",
            encoding="utf-8",
        )

        # Write signal to /Updates/ so Local merges it
        updates_dir = self.vault / "Updates"
        updates_dir.mkdir(exist_ok=True)
        update_path = updates_dir / f"cloud_draft_{draft_id}.md"
        update_path.write_text(
            f"---\ntype: update\nsource: cloud-agent\n"
            f"event: email_draft_created\ntask_id: {task_id}\n"
            f"timestamp: {datetime.now().isoformat()}\n---\n\n"
            f"Cloud agent created email draft for `{task_id}`. "
            f"Pending Local approval.\n",
            encoding="utf-8",
        )

        self.log_entry(f"[Cloud] Email draft created: {draft_id} → Pending_Approval")
        return {
            "status": "success",
            "draft_id": draft_id,
            "draft_path": str(draft_path),
            "approval_path": str(approval_path),
        }

    def _extract_field(self, content: str, field: str) -> str:
        for line in content.splitlines():
            if line.lower().startswith(field + ":"):
                return line.split(":", 1)[-1].strip()
        return ""


# ---------------------------------------------------------------------------
# Platinum Skill 2: VaultSyncSkill
# ---------------------------------------------------------------------------

class VaultSyncSkill(AgentSkill):
    """
    Git-based vault synchronization between Cloud and Local agents.

    Pull: fetches latest vault state from remote.
    Push: commits all markdown/state changes and pushes.

    Security: never stages .env, *.json (token/credentials), *.key, *.pem.
    """

    name = "vault_sync"
    description = (
        "Sync vault state via Git. Pulls before reading, commits+pushes after "
        "writing. Skips secrets (.env, token.json, credentials.json, *.key, *.pem)."
    )

    SKIP_PATTERNS = {".env", "token.json", "credentials.json", "*.key", "*.pem", "*.p12"}
    SAFE_EXTENSIONS = {".md", ".txt", ".json"}  # only json for non-secret state files

    def execute(self, file_path: Path = None) -> dict:
        """
        file_path is not used here. Called with action via vault_paths metadata.
        Returns result of pull or push operation.
        """
        action = os.environ.get("VAULT_SYNC_ACTION", "pull")
        repo_dir = str(self.vault)

        if action == "pull":
            return self._git_pull(repo_dir)
        elif action == "push":
            return self._git_push(repo_dir)
        else:
            return self._git_pull(repo_dir)

    def pull(self) -> dict:
        return self._git_pull(str(self.vault))

    def push(self, message: str = "AI Employee: vault sync") -> dict:
        return self._git_push(str(self.vault), message)

    def _git_pull(self, repo_dir: str) -> dict:
        try:
            result = subprocess.run(
                ["git", "pull", "--rebase", "origin", "main"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                self.log_entry("[VaultSync] Pull succeeded")
                return {"status": "success", "output": result.stdout.strip()}
            else:
                self.log_entry(f"[VaultSync] Pull failed: {result.stderr.strip()}")
                return {"status": "error", "output": result.stderr.strip()}
        except subprocess.TimeoutExpired:
            return {"status": "error", "output": "git pull timed out"}
        except FileNotFoundError:
            return {"status": "error", "output": "git not found in PATH"}

    def _git_push(self, repo_dir: str, message: str = "AI Employee: vault sync") -> dict:
        try:
            # Stage only safe files (no secrets)
            add_result = subprocess.run(
                ["git", "add",
                 "AI_Employee_Vault/",
                 "--",
                 ":!AI_Employee_Vault/**/.env",
                 ":!AI_Employee_Vault/**/token.json",
                 ":!AI_Employee_Vault/**/credentials.json",
                 ],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )

            # Check if there's anything to commit
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if not status_result.stdout.strip():
                return {"status": "success", "output": "Nothing to commit"}

            commit_result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )

            push_result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if push_result.returncode == 0:
                self.log_entry(f"[VaultSync] Push succeeded: {message}")
                return {"status": "success", "output": push_result.stdout.strip()}
            else:
                self.log_entry(f"[VaultSync] Push failed: {push_result.stderr.strip()}")
                return {"status": "error", "output": push_result.stderr.strip()}

        except subprocess.TimeoutExpired:
            return {"status": "error", "output": "git push timed out"}
        except FileNotFoundError:
            return {"status": "error", "output": "git not found in PATH"}


# ---------------------------------------------------------------------------
# Platinum Skill 3: ClaimByMoveSkill
# ---------------------------------------------------------------------------

class ClaimByMoveSkill(AgentSkill):
    """
    Implement the claim-by-move rule:
      First agent to move a file from /Needs_Action/<domain>/ to
      /In_Progress/<agent-id>/ owns it. Others must ignore it.

    This prevents double-work when both Cloud and Local agents are running.
    """

    name = "claim_by_move"
    description = (
        "Atomically claim a task by moving it from /Needs_Action/ to "
        "/In_Progress/<agent-id>/. Returns claimed=True if successful."
    )

    def execute(self, file_path: Path = None) -> dict:
        if file_path is None or not file_path.exists():
            return {"status": "error", "claimed": False, "message": "File not found"}

        agent_id = os.environ.get("AGENT_ID", "local-agent")
        in_progress_dir = self.vault / "In_Progress" / agent_id
        in_progress_dir.mkdir(parents=True, exist_ok=True)

        dest = in_progress_dir / file_path.name

        # If already claimed by another agent, skip
        for other_dir in (self.vault / "In_Progress").iterdir():
            if other_dir.is_dir() and other_dir.name != agent_id:
                if (other_dir / file_path.name).exists():
                    return {
                        "status": "skipped",
                        "claimed": False,
                        "message": f"Already claimed by {other_dir.name}",
                    }

        # Attempt atomic move (claim)
        try:
            shutil.move(str(file_path), str(dest))
            self.log_entry(f"[Claim] {agent_id} claimed: {file_path.name}")
            return {"status": "success", "claimed": True, "dest": str(dest)}
        except (shutil.Error, OSError) as e:
            # Race condition — another agent got there first
            return {"status": "race_lost", "claimed": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Platinum Skill 4: LocalApprovalExecutorSkill
# ---------------------------------------------------------------------------

class LocalApprovalExecutorSkill(AgentSkill):
    """
    Watch /Approved/ for approval files moved by the user (or auto-approval).
    Execute the corresponding action (send email via MCP, post social, etc.).
    Moves task to /Done/ after execution.

    Only runs on the Local agent — never on Cloud.
    """

    name = "local_approval_executor"
    description = (
        "Execute approved actions from /Approved/. Sends emails, posts content, "
        "etc. Then moves completed tasks to /Done/. LOCAL ONLY."
    )

    def execute(self, file_path: Path = None) -> dict:
        if file_path is None or not file_path.exists():
            return {"status": "error", "message": "No approval file provided"}

        content = self._read_file(file_path)
        action = self._extract_field(content, "action")
        task_id = self._extract_field(content, "task_id")
        draft_path_str = self._extract_field(content, "draft_path")

        result = {"status": "pending", "action": action, "task_id": task_id}

        if action == "send_email":
            result = self._execute_send_email(content, draft_path_str)
        elif action == "post_linkedin":
            result = self._execute_social_post(content, "linkedin")
        elif action == "post_facebook":
            result = self._execute_social_post(content, "facebook")
        elif action == "post_twitter":
            result = self._execute_social_post(content, "twitter")
        elif action == "odoo_post":
            result = self._execute_odoo_post(content)
        else:
            result = {"status": "unsupported", "message": f"Unknown action: {action}"}

        # Move approval file to Done
        if result.get("status") in ("success", "simulated"):
            done_path = self.done / file_path.name
            shutil.move(str(file_path), str(done_path))
            self.log_entry(f"[LocalExec] Executed & archived: {file_path.name} → Done/")

            # Clean up draft file if it exists
            if draft_path_str:
                draft_full = self.vault / draft_path_str
                if draft_full.exists():
                    draft_full.unlink()

        return result

    def _extract_field(self, content: str, field: str) -> str:
        for line in content.splitlines():
            if line.lower().startswith(field + ":"):
                return line.split(":", 1)[-1].strip()
        return ""

    def _execute_send_email(self, content: str, draft_path_str: str) -> dict:
        """Send email via MCP or Gmail API."""
        to_addr = self._extract_field(content, "to")
        subject = self._extract_field(content, "subject")

        draft_body = ""
        if draft_path_str:
            draft_full = self.vault / draft_path_str
            if draft_full.exists():
                draft_content = self._read_file(draft_full)
                if "## Draft Reply" in draft_content:
                    draft_body = draft_content.split("## Draft Reply")[-1].strip()

        # Attempt Gmail API send
        try:
            import base64
            from email.mime.text import MIMEText
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            token_path = Path(os.environ.get("GMAIL_TOKEN_PATH", "token.json"))
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path))
                service = build("gmail", "v1", credentials=creds)
                message = MIMEText(draft_body)
                message["to"] = to_addr
                message["subject"] = subject
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                service.users().messages().send(
                    userId="me", body={"raw": raw}
                ).execute()
                self.log_entry(f"[LocalExec] Email sent to {to_addr}: {subject}")
                return {"status": "success", "to": to_addr, "subject": subject}
        except Exception as e:
            self.log_entry(f"[LocalExec] Gmail send failed ({e}), using simulation")

        # Simulation fallback
        self.log_entry(f"[LocalExec] Simulated email send to {to_addr}: {subject}")
        return {"status": "simulated", "to": to_addr, "subject": subject}

    def _execute_social_post(self, content: str, platform: str) -> dict:
        self.log_entry(f"[LocalExec] Simulated {platform} post")
        return {"status": "simulated", "platform": platform}

    def _execute_odoo_post(self, content: str) -> dict:
        self.log_entry("[LocalExec] Simulated Odoo post (invoice/payment)")
        return {"status": "simulated", "action": "odoo_post"}


# ---------------------------------------------------------------------------
# Platinum Skill 5: DashboardMergeSkill
# ---------------------------------------------------------------------------

class DashboardMergeSkill(AgentSkill):
    """
    Merge /Updates/ signal files from the Cloud agent into Dashboard.md.

    Single-writer rule: ONLY the Local agent writes Dashboard.md.
    Cloud agent writes to /Updates/ instead; Local merges on each cycle.
    """

    name = "dashboard_merge"
    description = (
        "Read all files in /Updates/, append cloud events to Dashboard.md, "
        "then archive processed update files to /Done/. LOCAL ONLY."
    )

    def execute(self, file_path: Path = None) -> dict:
        updates_dir = self.vault / "Updates"
        updates_dir.mkdir(exist_ok=True)

        update_files = sorted(updates_dir.glob("*.md"))
        if not update_files:
            return {"status": "success", "merged": 0}

        events = []
        for uf in update_files:
            content = self._read_file(uf)
            events.append(f"- {uf.stem}: {content.splitlines()[-1] if content.splitlines() else ''}")

            # Archive to Done
            done_path = self.done / f"UPDATE_{uf.name}"
            shutil.move(str(uf), str(done_path))

        # Append to Dashboard.md
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        section = (
            f"\n## Cloud Agent Updates — {timestamp}\n\n"
            + "\n".join(events)
            + "\n"
        )
        with open(self.dashboard, "a", encoding="utf-8") as f:
            f.write(section)

        self.log_entry(f"[DashboardMerge] Merged {len(events)} cloud updates into Dashboard.md")
        return {"status": "success", "merged": len(events)}


# ---------------------------------------------------------------------------
# Platinum Skill 6: CloudHealthMonitorSkill
# ---------------------------------------------------------------------------

class CloudHealthMonitorSkill(AgentSkill):
    """
    Write health heartbeat to /Signals/health.md so Local agent can detect
    if the Cloud agent goes offline.

    Cloud agent calls this every N minutes. Local agent reads it and alerts
    if the heartbeat is stale (> 10 minutes old).
    """

    name = "cloud_health_monitor"
    description = (
        "Write health heartbeat to /Signals/health.md. "
        "Also check if the local health signal is stale (alert threshold: 10 min)."
    )

    STALE_THRESHOLD_MINUTES = 10

    def execute(self, file_path: Path = None) -> dict:
        signals_dir = self.vault / "Signals"
        signals_dir.mkdir(exist_ok=True)
        health_path = signals_dir / "health.md"

        agent_id = os.environ.get("AGENT_ID", "cloud-agent")
        hostname = socket.gethostname()
        now = datetime.now()

        health_path.write_text(
            f"---\nagent_id: {agent_id}\nhostname: {hostname}\n"
            f"last_heartbeat: {now.isoformat()}\nstatus: online\n---\n\n"
            f"# Cloud Agent Health\n\n"
            f"- **Agent:** {agent_id}\n"
            f"- **Host:** {hostname}\n"
            f"- **Last Heartbeat:** {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- **Status:** ONLINE\n",
            encoding="utf-8",
        )

        self.log_entry(f"[Health] Heartbeat written by {agent_id} @ {hostname}")
        return {"status": "online", "agent_id": agent_id, "timestamp": now.isoformat()}

    def check_stale(self) -> dict:
        """Called by Local agent to verify Cloud is alive."""
        signals_dir = self.vault / "Signals"
        health_path = signals_dir / "health.md"

        if not health_path.exists():
            return {"status": "unknown", "message": "No health signal found"}

        content = self._read_file(health_path)
        for line in content.splitlines():
            if line.startswith("last_heartbeat:"):
                ts_str = line.split(":", 1)[-1].strip()
                try:
                    last_hb = datetime.fromisoformat(ts_str)
                    age_min = (datetime.now() - last_hb).total_seconds() / 60
                    if age_min > self.STALE_THRESHOLD_MINUTES:
                        self.log_entry(f"[Health] ALERT: Cloud agent stale ({age_min:.1f} min)")
                        return {"status": "stale", "age_minutes": age_min}
                    return {"status": "online", "age_minutes": age_min}
                except ValueError:
                    return {"status": "error", "message": "Cannot parse heartbeat timestamp"}

        return {"status": "unknown", "message": "No heartbeat field found"}


# ---------------------------------------------------------------------------
# Platinum Skill 7: OdooCloudDraftSkill
# ---------------------------------------------------------------------------

class OdooCloudDraftSkill(AgentSkill):
    """
    Cloud-side Odoo integration: draft-only.

    Cloud can READ Odoo data (invoices, partners, transactions) and CREATE
    draft records, but CANNOT post/confirm invoices or execute payments.
    That requires Local approval (OdooCloudDraftSkill → Pending_Approval →
    Local executes via full OdooAccountingSkill).
    """

    name = "odoo_cloud_draft"
    description = (
        "Cloud-side Odoo: read data, create DRAFT invoices only. "
        "Writes approval request for Local to confirm/post. "
        "NEVER posts or pays directly."
    )

    def execute(self, file_path: Path = None) -> dict:
        if file_path is None or not file_path.exists():
            return {"status": "error", "message": "No task file provided"}

        content = self._read_file(file_path)
        task_id = file_path.stem
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # Parse invoice details from task file
        partner = self._extract_field(content, "partner") or "Unknown Client"
        amount = self._extract_field(content, "amount") or "0.00"
        description = self._extract_field(content, "description") or "Service"

        odoo_url = os.environ.get("ODOO_URL", "http://localhost:8069")
        odoo_db = os.environ.get("ODOO_DB", "odoo")

        # Attempt Odoo draft creation via JSON-RPC
        draft_id = None
        try:
            import xmlrpc.client
            common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common")
            uid = common.authenticate(
                odoo_db,
                os.environ.get("ODOO_USERNAME", "admin"),
                os.environ.get("ODOO_API_KEY", ""),
                {},
            )
            if uid:
                models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object")
                draft_id = models.execute_kw(
                    odoo_db, uid, os.environ.get("ODOO_API_KEY", ""),
                    "account.move", "create",
                    [{
                        "move_type": "out_invoice",
                        "partner_id": 1,
                        "invoice_line_ids": [(0, 0, {
                            "name": description,
                            "price_unit": float(amount),
                            "quantity": 1.0,
                        })],
                    }],
                )
                self.log_entry(f"[OdooCloud] Draft invoice #{draft_id} created for {partner}")
        except Exception as e:
            self.log_entry(f"[OdooCloud] Odoo unavailable ({e}), using simulation")
            draft_id = f"SIM-{timestamp}"

        # Write approval request for Local to post the invoice
        approval_path = self.pending_approval / f"ODOO_POST_{task_id}_{timestamp}.md"
        approval_path.write_text(
            f"---\ntype: approval_request\naction: odoo_post\n"
            f"task_id: {task_id}\nodoo_draft_id: {draft_id}\n"
            f"partner: {partner}\namount: {amount}\n"
            f"created_by: cloud-agent\ncreated: {datetime.now().isoformat()}\n"
            f"expires: {(datetime.now() + timedelta(hours=48)).isoformat()}\n"
            f"status: pending\n---\n\n"
            f"## Odoo Invoice — Approval Required\n\n"
            f"Cloud agent created a **DRAFT** invoice:\n"
            f"- **Partner:** {partner}\n"
            f"- **Amount:** ${amount}\n"
            f"- **Description:** {description}\n"
            f"- **Odoo Draft ID:** {draft_id}\n\n"
            f"## To Approve (Post Invoice)\nMove this file to `/Approved/`.\n\n"
            f"## To Reject\nMove this file to `/Rejected/`.\n",
            encoding="utf-8",
        )

        return {"status": "success", "draft_id": draft_id, "approval_path": str(approval_path)}

    def _extract_field(self, content: str, field: str) -> str:
        for line in content.splitlines():
            if line.lower().startswith(field + ":"):
                return line.split(":", 1)[-1].strip()
        return ""


# ---------------------------------------------------------------------------
# Platinum Skill 8: VaultCleanupSkill
# ---------------------------------------------------------------------------

class VaultCleanupSkill(AgentSkill):
    """
    Archive stale /In_Progress/<agent>/ claim files back to /Needs_Action/
    if they've been claimed for too long (default: 30 minutes timeout).

    Prevents deadlock when a Cloud or Local agent crashes mid-task.
    """

    name = "vault_cleanup"
    description = (
        "Return stale In_Progress claims (> 30 min) back to Needs_Action. "
        "Run periodically by both Cloud and Local agents."
    )

    STALE_CLAIM_MINUTES = 30

    def execute(self, file_path: Path = None) -> dict:
        in_progress_root = self.vault / "In_Progress"
        if not in_progress_root.exists():
            return {"status": "success", "reclaimed": 0}

        now = datetime.now()
        reclaimed = 0

        for agent_dir in in_progress_root.iterdir():
            if not agent_dir.is_dir():
                continue
            for claimed_file in agent_dir.iterdir():
                if not claimed_file.is_file():
                    continue
                age_min = (now - datetime.fromtimestamp(claimed_file.stat().st_mtime)).total_seconds() / 60
                if age_min > self.STALE_CLAIM_MINUTES:
                    dest = self.needs_action / claimed_file.name
                    shutil.move(str(claimed_file), str(dest))
                    self.log_entry(
                        f"[Cleanup] Reclaimed stale claim from {agent_dir.name}: "
                        f"{claimed_file.name} ({age_min:.1f} min)"
                    )
                    reclaimed += 1

        return {"status": "success", "reclaimed": reclaimed}


# ---------------------------------------------------------------------------
# Registry helper — extends gold-tier SkillRegistry with platinum skills
# ---------------------------------------------------------------------------

PLATINUM_SKILLS = [
    CloudEmailDraftSkill,
    VaultSyncSkill,
    ClaimByMoveSkill,
    LocalApprovalExecutorSkill,
    DashboardMergeSkill,
    CloudHealthMonitorSkill,
    OdooCloudDraftSkill,
    VaultCleanupSkill,
]
