"""
Cloud Agent — Always-On Cloud-Side Orchestrator (Platinum Tier).

Runs 24/7 on Oracle Cloud Free VM (or AWS/GCP equivalent).
This is the "draft-only" agent — it processes inputs and creates approval
files for the Local agent, but NEVER executes sensitive actions directly.

Work-Zone Specialization (Platinum Rule):
  CLOUD OWNS:
    - Email triage + draft replies (writes to /Pending_Approval/)
    - Social post drafts/scheduling (writes to /Pending_Approval/)
    - Odoo draft invoice creation (writes to /Pending_Approval/)
    - Vault sync via Git (pull before read, push after write)
    - Health heartbeat to /Signals/health.md

  LOCAL OWNS (never done here):
    - WhatsApp sessions and replies
    - Banking, payments, payment tokens
    - Final "send/post" execution
    - Dashboard.md updates (single-writer rule)

Security rules enforced here:
  - Never read/write WhatsApp session, banking creds, payment tokens
  - All secrets in local .env (never in vault)
  - Vault sync only pushes markdown (VaultSync enforces this)
  - After each write cycle: git push vault state

Usage (on cloud VM):
    python cloud_agent.py [--vault-path PATH] [--interval SECONDS]

Deployment: use health_monitor.py as a watchdog process.
See cloud_deploy/ for systemd service files and Oracle Cloud setup.
"""

import os
import sys
import time
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
    CloudEmailDraftSkill,
    ClaimByMoveSkill,
    CloudHealthMonitorSkill,
    OdooCloudDraftSkill,
    VaultCleanupSkill,
    VaultSyncSkill,
    PLATINUM_SKILLS,
)
from agent_skills import SkillRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CloudAgent] %(levelname)s: %(message)s",
)
logger = logging.getLogger("CloudAgent")

# Cloud agent identity
AGENT_ID = os.environ.get("AGENT_ID", "cloud-agent")
os.environ["AGENT_ID"] = AGENT_ID


class CloudAgent:
    """
    Platinum Tier Cloud-side orchestrator.

    Cycle (every N seconds):
      1. Pull vault state from git
      2. Claim new tasks from /Needs_Action/ (claim-by-move)
      3. Triage emails → draft replies → write to /Pending_Approval/
      4. Draft social posts → write to /Pending_Approval/
      5. Draft Odoo records → write to /Pending_Approval/
      6. Write health heartbeat to /Signals/health.md
      7. Cleanup stale In_Progress claims
      8. Push vault state to git
    """

    def __init__(self, vault_path: str, check_interval: int = 60):
        self.vault_path = Path(vault_path)
        self.check_interval = check_interval

        # Vault directories — cloud can write to these
        self.needs_action = self.vault_path / "Needs_Action"
        self.pending_approval = self.vault_path / "Pending_Approval"
        self.plans = self.vault_path / "Plans"
        self.done = self.vault_path / "Done"
        self.drafts = self.vault_path / "Drafts"
        self.updates = self.vault_path / "Updates"
        self.signals = self.vault_path / "Signals"
        self.in_progress = self.vault_path / "In_Progress" / AGENT_ID
        self.logs_dir = self.vault_path / "Logs"
        self.system_logs = self.vault_path / "System_Logs.md"

        # Cloud does NOT own Dashboard.md (Local is single writer)
        self.dashboard = self.vault_path / "Dashboard.md"

        # Create cloud-owned directories
        for d in [
            self.needs_action, self.pending_approval, self.plans,
            self.done, self.drafts, self.updates, self.signals,
            self.in_progress, self.logs_dir,
            self.vault_path / "In_Progress",
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Initialize vault sync
        self.vault_sync = VaultSync(repo_dir=str(self.vault_path.parent))
        self.vault_sync.ensure_gitignore()

        # Initialize skill registry with all gold + platinum skills
        vault_paths = self._build_vault_paths()
        self.registry = SkillRegistry(vault_paths)
        self._register_skills(vault_paths)

        # Domain-specific skill instances
        self.email_draft_skill = CloudEmailDraftSkill(vault_paths)
        self.claim_skill = ClaimByMoveSkill(vault_paths)
        self.health_skill = CloudHealthMonitorSkill(vault_paths)
        self.odoo_skill = OdooCloudDraftSkill(vault_paths)
        self.cleanup_skill = VaultCleanupSkill(vault_paths)

        self.processed_files = set()
        self.running = False
        self.cycle_count = 0

    def _build_vault_paths(self) -> dict:
        return {
            "vault": self.vault_path,
            "inbox": self.vault_path / "Inbox",
            "needs_action": self.needs_action,
            "done": self.done,
            "system_logs": self.system_logs,
            "dashboard": self.dashboard,
            "plans": self.plans,
            "pending_approval": self.pending_approval,
            "approved": self.vault_path / "Approved",
            "rejected": self.vault_path / "Rejected",
            "logs_dir": self.logs_dir,
        }

    def _register_skills(self, vault_paths: dict):
        """Register all platinum skills."""
        for skill_cls in PLATINUM_SKILLS:
            self.registry.register(skill_cls)

    def log(self, message: str):
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M]")
        entry = f"| {timestamp} | [CLOUD] {message} |\n"
        with open(self.system_logs, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(message)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        self.running = True
        self.log(f"Cloud Agent started (ID: {AGENT_ID}, interval: {self.check_interval}s)")

        while self.running:
            try:
                self._run_cycle()
            except KeyboardInterrupt:
                self.log("Cloud Agent shutting down (KeyboardInterrupt)")
                break
            except Exception as e:
                self.log(f"ERROR in cycle: {e}")
                logger.exception("Unhandled error in cycle")

            time.sleep(self.check_interval)

    def _run_cycle(self):
        self.cycle_count += 1
        self.log(f"=== Cycle #{self.cycle_count} ===")

        # Step 1: Pull latest vault state
        pull_result = self.vault_sync.pull()
        if pull_result["status"] == "error":
            self.log(f"Vault pull failed: {pull_result['output']}")
            # Continue anyway — work with current local state

        # Step 2: Write health heartbeat
        self.health_skill.execute()

        # Step 3: Cleanup stale In_Progress claims
        cleanup = self.cleanup_skill.execute()
        if cleanup.get("reclaimed", 0) > 0:
            self.log(f"Reclaimed {cleanup['reclaimed']} stale claim(s)")

        # Step 4: Process new tasks from /Needs_Action/
        self._process_needs_action()

        # Step 5: Process cloud-specific subfolders
        self._process_cloud_needs_action()

        # Step 6: Push vault state
        push_result = self.vault_sync.push(
            f"Cloud Agent cycle #{self.cycle_count}: processed tasks"
        )
        if push_result["status"] == "error":
            self.log(f"Vault push failed: {push_result['output']}")

    def _process_needs_action(self):
        """Process top-level /Needs_Action/ files."""
        if not self.needs_action.exists():
            return

        for task_file in list(self.needs_action.iterdir()):
            if not task_file.is_file():
                continue
            if task_file.name in self.processed_files:
                continue

            # Claim the task (claim-by-move rule)
            claim_result = self.claim_skill.execute(task_file)
            if not claim_result.get("claimed"):
                continue  # Another agent claimed it or race lost

            claimed_file = Path(claim_result["dest"])
            self.processed_files.add(task_file.name)
            self.log(f"Claimed: {task_file.name}")

            # Determine task type and route
            self._route_task(claimed_file)

    def _process_cloud_needs_action(self):
        """Process /Needs_Action/cloud/ domain subfolder."""
        cloud_na = self.needs_action / "cloud"
        cloud_na.mkdir(exist_ok=True)

        for task_file in list(cloud_na.iterdir()):
            if not task_file.is_file():
                continue
            if task_file.name in self.processed_files:
                continue

            claim_result = self.claim_skill.execute(task_file)
            if not claim_result.get("claimed"):
                continue

            claimed_file = Path(claim_result["dest"])
            self.processed_files.add(task_file.name)
            self.log(f"Claimed (cloud domain): {task_file.name}")
            self._route_task(claimed_file)

    def _route_task(self, claimed_file: Path):
        """Route a claimed task to the appropriate cloud skill."""
        name_lower = claimed_file.name.lower()
        content = self._read_file(claimed_file)
        task_type = self._extract_field(content, "type")

        try:
            if "email" in name_lower or task_type == "email":
                self._handle_email_task(claimed_file)
            elif "invoice" in name_lower or task_type in ("invoice", "accounting"):
                self._handle_odoo_task(claimed_file)
            elif any(kw in name_lower for kw in ("linkedin", "facebook", "twitter", "social")):
                self._handle_social_draft(claimed_file)
            else:
                # Generic: create a draft approval request
                self._handle_generic_task(claimed_file)
        except Exception as e:
            self.log(f"Error routing {claimed_file.name}: {e}")
            # Return to needs_action on error
            dest = self.needs_action / claimed_file.name
            try:
                import shutil
                shutil.move(str(claimed_file), str(dest))
            except Exception:
                pass

    def _handle_email_task(self, task_file: Path):
        """Draft a reply for an email task."""
        result = self.email_draft_skill.execute(task_file)
        if result.get("status") == "success":
            self.log(f"Email draft created: {result.get('draft_id')}")
            # Move claimed file to Done (draft is in Pending_Approval)
            done_path = self.done / task_file.name
            import shutil
            shutil.move(str(task_file), str(done_path))
        else:
            self.log(f"Email draft failed: {result.get('message')}")

    def _handle_odoo_task(self, task_file: Path):
        """Create a draft Odoo invoice."""
        result = self.odoo_skill.execute(task_file)
        if result.get("status") == "success":
            self.log(f"Odoo draft created: {result.get('draft_id')}")
            done_path = self.done / task_file.name
            import shutil
            shutil.move(str(task_file), str(done_path))
        else:
            self.log(f"Odoo draft failed: {result.get('message')}")

    def _handle_social_draft(self, task_file: Path):
        """Create a social media post draft for Local approval."""
        content = self._read_file(task_file)
        task_id = task_file.stem
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # Determine platform
        name_lower = task_file.name.lower()
        if "linkedin" in name_lower:
            platform = "linkedin"
        elif "facebook" in name_lower:
            platform = "facebook"
        elif "twitter" in name_lower:
            platform = "twitter"
        else:
            platform = "social"

        # Write approval request
        approval_path = self.pending_approval / f"SOCIAL_{platform.upper()}_{task_id}_{timestamp}.md"
        approval_path.write_text(
            f"---\ntype: approval_request\naction: post_{platform}\n"
            f"task_id: {task_id}\nplatform: {platform}\n"
            f"created_by: cloud-agent\ncreated: {datetime.now().isoformat()}\n"
            f"status: pending\n---\n\n"
            f"## Social Media Post — Approval Required\n\n"
            f"**Platform:** {platform.title()}\n\n"
            f"**Draft Content:**\n\n{content[:500]}\n\n"
            f"## To Approve\nMove this file to `/Approved/`.\n\n"
            f"## To Reject\nMove this file to `/Rejected/`.\n",
            encoding="utf-8",
        )

        # Write update signal
        update_path = self.updates / f"cloud_social_{task_id}_{timestamp}.md"
        update_path.write_text(
            f"---\ntype: update\nsource: cloud-agent\n"
            f"event: social_draft_created\ntask_id: {task_id}\nplatform: {platform}\n"
            f"timestamp: {datetime.now().isoformat()}\n---\n\n"
            f"Cloud agent created {platform} post draft for `{task_id}`. Awaiting Local approval.\n",
            encoding="utf-8",
        )

        self.log(f"Social draft ({platform}) created: {task_id}")
        done_path = self.done / task_file.name
        import shutil
        shutil.move(str(task_file), str(done_path))

    def _handle_generic_task(self, task_file: Path):
        """For unknown tasks, create a generic approval request."""
        content = self._read_file(task_file)
        task_id = task_file.stem
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        approval_path = self.pending_approval / f"GENERIC_{task_id}_{timestamp}.md"
        approval_path.write_text(
            f"---\ntype: approval_request\naction: review\n"
            f"task_id: {task_id}\ncreated_by: cloud-agent\n"
            f"created: {datetime.now().isoformat()}\nstatus: pending\n---\n\n"
            f"## Task Review — Cloud Agent\n\n"
            f"Cloud agent processed task `{task_id}` but could not determine action type.\n\n"
            f"**Original content:**\n\n{content[:800]}\n\n"
            f"## To Approve (execute as-is)\nMove to `/Approved/`.\n\n"
            f"## To Reject\nMove to `/Rejected/`.\n",
            encoding="utf-8",
        )
        self.log(f"Generic approval created for: {task_id}")
        done_path = self.done / task_file.name
        import shutil
        shutil.move(str(task_file), str(done_path))

    def _read_file(self, path: Path) -> str:
        for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1252"):
            try:
                return path.read_text(encoding=enc)
            except (UnicodeDecodeError, ValueError):
                continue
        return ""

    def _extract_field(self, content: str, field: str) -> str:
        for line in content.splitlines():
            if line.lower().startswith(field + ":"):
                return line.split(":", 1)[-1].strip()
        return ""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AI Employee — Cloud Agent (Platinum Tier)")
    parser.add_argument(
        "--vault-path",
        default=os.environ.get("VAULT_PATH", "AI_Employee_Vault"),
        help="Path to the AI Employee Vault directory",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("CLOUD_AGENT_INTERVAL", "60")),
        help="Check interval in seconds (default: 60)",
    )
    args = parser.parse_args()

    agent = CloudAgent(vault_path=args.vault_path, check_interval=args.interval)
    agent.run()


if __name__ == "__main__":
    main()
