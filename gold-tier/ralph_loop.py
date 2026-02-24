"""
Ralph Wiggum Autonomous Loop — Executes Plan.md steps sequentially.

Parses Plan.md checklist files, executes steps by matching against
registered skills, and marks steps as complete. Stops when all steps
are done, max iterations hit, or approval is needed.

Uses a claim-by-move pattern with In_Progress/ folder to prevent
duplicate processing.

Gold Tier — Phase 2: Ralph Wiggum Loop.
"""

import re
import shutil
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("RalphLoop")


class RalphWiggumLoop:
    """Parses and executes Plan.md checklist steps autonomously."""

    # Keywords that map plan steps to skill names
    SKILL_KEYWORDS = {
        "classify": ["classify", "urgency", "categorize", "triage"],
        "move_to_done": ["move to done", "complete", "archive", "close"],
        "update_dashboard": ["dashboard", "update dashboard"],
        "task_planner": ["plan", "break down", "action plan"],
        "gmail_send": ["email", "send email", "draft email", "gmail"],
        "linkedin_post": ["linkedin post", "linkedin draft"],
        "linkedin_auto_post": ["post to linkedin", "publish linkedin", "auto post"],
        "whatsapp_reply": ["whatsapp", "reply whatsapp"],
        "human_approval": ["approval", "human review", "flag for review"],
        "ceo_briefing": ["briefing", "ceo briefing", "executive summary"],
        "audit_log": ["audit", "log action", "audit log"],
        "odoo_accounting": ["invoice", "payment", "balance", "accounting", "odoo"],
        "facebook_post": ["facebook", "post to facebook", "fb post"],
        "instagram_post": ["instagram", "post to instagram", "ig post"],
        "twitter_post": ["twitter", "tweet", "post to twitter"],
        "social_media_summary": ["social media summary", "engagement summary"],
        "weekly_business_audit": ["weekly audit", "business audit"],
        "error_recovery": ["retry", "error recovery", "recover"],
    }

    def __init__(self, vault_path: Path, registry=None, max_iterations: int = 50):
        self.vault_path = Path(vault_path)
        self.registry = registry
        self.max_iterations = max_iterations
        self.plans_dir = self.vault_path / "Plans"
        self.in_progress_dir = self.vault_path / "In_Progress"
        self.done_dir = self.vault_path / "Done"
        self.in_progress_dir.mkdir(parents=True, exist_ok=True)
        self.iteration_count = 0
        self.completed_steps = 0
        self.skipped_steps = 0

    def find_active_plans(self) -> list[Path]:
        """Find Plan.md files with unchecked steps."""
        plans = []
        if not self.plans_dir.exists():
            return plans

        for f in sorted(self.plans_dir.iterdir()):
            if f.is_file() and f.suffix == ".md":
                content = f.read_text(encoding="utf-8")
                if "- [ ]" in content:
                    # Check if not requiring approval
                    if "approval_required: True" not in content or "status: ready" in content:
                        plans.append(f)
        return plans

    def parse_steps(self, plan_content: str) -> list[dict]:
        """Parse checklist steps from Plan.md content."""
        steps = []
        for line in plan_content.splitlines():
            checked_match = re.match(r"^- \[x\] (.+)$", line.strip())
            unchecked_match = re.match(r"^- \[ \] (.+)$", line.strip())
            if checked_match:
                steps.append({"text": checked_match.group(1), "done": True})
            elif unchecked_match:
                steps.append({"text": unchecked_match.group(1), "done": False})
        return steps

    def match_skill(self, step_text: str) -> str | None:
        """Match a step description to a skill name using keywords."""
        step_lower = step_text.lower()
        for skill_name, keywords in self.SKILL_KEYWORDS.items():
            for kw in keywords:
                if kw in step_lower:
                    return skill_name
        return None

    def claim_plan(self, plan_path: Path) -> Path | None:
        """Claim a plan by moving it to In_Progress/."""
        try:
            dest = self.in_progress_dir / plan_path.name
            if dest.exists():
                return None  # Already claimed
            shutil.copy2(str(plan_path), str(dest))
            return dest
        except Exception as e:
            logger.error(f"Failed to claim plan {plan_path.name}: {e}")
            return None

    def release_plan(self, in_progress_path: Path, original_path: Path, plan_content: str):
        """Release a plan back with updated content."""
        original_path.write_text(plan_content, encoding="utf-8")
        if in_progress_path.exists():
            in_progress_path.unlink()

    def mark_step_done(self, plan_content: str, step_text: str) -> str:
        """Mark a specific step as done in plan content."""
        old = f"- [ ] {step_text}"
        new = f"- [x] {step_text}"
        return plan_content.replace(old, new, 1)

    def execute_step(self, step_text: str, source_file: Path = None) -> dict:
        """Execute a single plan step by matching it to a skill."""
        skill_name = self.match_skill(step_text)

        if not skill_name:
            logger.info(f"No skill matched for step: {step_text}")
            return {"status": "skipped", "reason": "no_matching_skill", "step": step_text}

        if self.registry and skill_name in self.registry.list_skills():
            try:
                result = self.registry.run(skill_name, source_file)
                result["status"] = "completed"
                result["skill_used"] = skill_name
                return result
            except Exception as e:
                logger.error(f"Error executing {skill_name}: {e}")
                return {"status": "error", "skill": skill_name, "error": str(e)}
        else:
            return {"status": "skipped", "reason": "skill_not_registered", "skill": skill_name}

    def needs_approval(self, step_text: str) -> bool:
        """Check if a step requires human approval before execution."""
        approval_keywords = ["payment", "delete", "send email", "transfer", "publish"]
        step_lower = step_text.lower()
        return any(kw in step_lower for kw in approval_keywords)

    def execute_plan(self, plan_path: Path) -> dict:
        """Execute all unchecked steps in a plan."""
        content = plan_path.read_text(encoding="utf-8")
        steps = self.parse_steps(content)

        # Extract source file from plan metadata
        source_file = None
        for line in content.splitlines():
            if line.startswith("source_file:"):
                source_name = line.split(":", 1)[1].strip()
                potential = self.vault_path / "Needs_Action" / source_name
                if potential.exists():
                    source_file = potential
                break

        results = []
        steps_completed = 0
        steps_skipped = 0
        approval_needed = False

        for step in steps:
            if step["done"]:
                continue

            self.iteration_count += 1
            if self.iteration_count > self.max_iterations:
                logger.warning("Max iterations reached, stopping")
                break

            if self.needs_approval(step["text"]):
                approval_needed = True
                results.append({"step": step["text"], "status": "needs_approval"})
                steps_skipped += 1
                continue

            result = self.execute_step(step["text"], source_file)
            results.append(result)

            if result.get("status") == "completed":
                content = self.mark_step_done(content, step["text"])
                steps_completed += 1
                self.completed_steps += 1
            else:
                steps_skipped += 1
                self.skipped_steps += 1

        # Write back updated plan
        plan_path.write_text(content, encoding="utf-8")

        # Check if all steps are done
        remaining = content.count("- [ ]")
        all_done = remaining == 0

        # Update plan status if all done
        if all_done and "status: ready" in content:
            content = content.replace("status: ready", "status: completed")
            plan_path.write_text(content, encoding="utf-8")

        return {
            "plan": plan_path.name,
            "steps_completed": steps_completed,
            "steps_skipped": steps_skipped,
            "all_done": all_done,
            "remaining": remaining,
            "approval_needed": approval_needed,
            "results": results,
        }

    def run(self) -> dict:
        """Main loop: find and execute all active plans."""
        self.iteration_count = 0
        self.completed_steps = 0
        self.skipped_steps = 0

        plans = self.find_active_plans()
        if not plans:
            return {"status": "idle", "message": "No active plans found", "plans_processed": 0}

        all_results = []
        for plan_path in plans:
            if self.iteration_count >= self.max_iterations:
                break

            claimed = self.claim_plan(plan_path)
            if not claimed:
                continue

            logger.info(f"Executing plan: {plan_path.name}")
            result = self.execute_plan(plan_path)
            self.release_plan(claimed, plan_path, plan_path.read_text(encoding="utf-8"))
            all_results.append(result)

        return {
            "status": "completed",
            "plans_processed": len(all_results),
            "total_steps_completed": self.completed_steps,
            "total_steps_skipped": self.skipped_steps,
            "iterations_used": self.iteration_count,
            "results": all_results,
        }

    def get_stats(self) -> dict:
        active_plans = len(self.find_active_plans())
        in_progress = len(list(self.in_progress_dir.iterdir())) if self.in_progress_dir.exists() else 0
        return {
            "active_plans": active_plans,
            "in_progress": in_progress,
            "completed_steps": self.completed_steps,
            "skipped_steps": self.skipped_steps,
            "iterations_used": self.iteration_count,
            "max_iterations": self.max_iterations,
        }
