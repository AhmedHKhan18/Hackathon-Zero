"""
Vault Sync — Git-based synchronization between Cloud and Local agents.

Platinum Tier: Cloud and Local share state via a private Git repository.
This module provides sync primitives used by both cloud_agent.py and local_agent.py.

Security rules:
  - Never stages: .env, token.json, credentials.json, *.key, *.pem, *.p12
  - Only syncs: AI_Employee_Vault/ (markdown + state files)
  - Secrets stay local; each side has its own .env

Usage:
    sync = VaultSync(repo_dir="/path/to/platinum-tier")
    sync.pull()                          # Before reading vault
    sync.push("AI Employee: new draft")  # After writing vault
"""

import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("VaultSync")


# Patterns to NEVER stage — secrets must never cross the network
SECRET_PATTERNS = [
    ".env",
    "token.json",
    "credentials.json",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "linkedin_session/",
    "whatsapp_session/",
    "venv/",
    "__pycache__/",
    ".pytest_cache/",
]


class VaultSync:
    """Git-based vault synchronization."""

    def __init__(self, repo_dir: str = None):
        self.repo_dir = Path(repo_dir or os.environ.get("VAULT_REPO_DIR", "."))
        self.branch = os.environ.get("VAULT_SYNC_BRANCH", "main")
        self.remote = os.environ.get("VAULT_SYNC_REMOTE", "origin")
        self.agent_id = os.environ.get("AGENT_ID", "agent")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pull(self) -> dict:
        """Pull latest vault state from remote. Call before reading vault."""
        logger.info(f"[VaultSync] Pulling from {self.remote}/{self.branch}")
        return self._run_git(
            ["git", "pull", "--rebase", self.remote, self.branch],
            timeout=30,
            op="pull",
        )

    def push(self, message: str = None) -> dict:
        """Commit safe files and push to remote. Call after writing to vault."""
        if message is None:
            message = f"AI Employee [{self.agent_id}]: vault sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        # Stage vault markdown/state (exclude secrets)
        stage = self._stage_vault_files()
        if not stage.get("has_changes"):
            logger.info("[VaultSync] Nothing to commit")
            return {"status": "success", "output": "Nothing to commit"}

        commit = self._run_git(["git", "commit", "-m", message], timeout=15, op="commit")
        if commit["status"] != "success":
            return commit

        push = self._run_git(
            ["git", "push", self.remote, self.branch], timeout=30, op="push"
        )
        logger.info(f"[VaultSync] Push result: {push['status']}")
        return push

    def status(self) -> dict:
        """Return git status output."""
        return self._run_git(["git", "status", "--short"], timeout=10, op="status")

    def ensure_gitignore(self):
        """Make sure .gitignore excludes secrets. Creates/updates if needed."""
        gitignore = self.repo_dir / ".gitignore"
        required_lines = set(SECRET_PATTERNS + [
            ".env", "*.env", "venv/", "__pycache__/", "*.pyc",
            "token.json", "credentials.json", "linkedin_session/",
        ])

        existing = set()
        if gitignore.exists():
            existing = set(gitignore.read_text(encoding="utf-8").splitlines())

        missing = required_lines - existing
        if missing:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write("\n# Platinum Tier — auto-added secrets exclusions\n")
                for line in sorted(missing):
                    f.write(f"{line}\n")
            logger.info(f"[VaultSync] Added {len(missing)} entries to .gitignore")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _stage_vault_files(self) -> dict:
        """Stage only AI_Employee_Vault/ markdown and state files."""
        vault_dir = self.repo_dir / "AI_Employee_Vault"
        if not vault_dir.exists():
            return {"has_changes": False}

        # Add vault dir (git will respect .gitignore for secrets)
        add_result = self._run_git(
            ["git", "add", "AI_Employee_Vault/"], timeout=15, op="add"
        )

        # Check if anything was staged
        diff_result = self._run_git(
            ["git", "diff", "--cached", "--name-only"], timeout=10, op="diff"
        )
        has_changes = bool(diff_result.get("output", "").strip())
        return {"has_changes": has_changes, "staged_files": diff_result.get("output", "")}

    def _run_git(self, cmd: list, timeout: int = 30, op: str = "") -> dict:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return {"status": "success", "output": result.stdout.strip(), "op": op}
            else:
                # git pull with "Already up to date" is not an error
                combined = (result.stdout + result.stderr).strip()
                if "Already up to date" in combined or "nothing to commit" in combined.lower():
                    return {"status": "success", "output": combined, "op": op}
                logger.warning(f"[VaultSync] {op} failed: {combined}")
                return {"status": "error", "output": combined, "op": op}
        except subprocess.TimeoutExpired:
            return {"status": "error", "output": f"{op} timed out after {timeout}s", "op": op}
        except FileNotFoundError:
            return {"status": "error", "output": "git not found in PATH", "op": op}


# ------------------------------------------------------------------
# Stand-alone usage
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vault Git Sync")
    parser.add_argument("action", choices=["pull", "push", "status"], help="Sync action")
    parser.add_argument("--repo-dir", default=".", help="Path to repo root")
    parser.add_argument("--message", default=None, help="Commit message (push only)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    sync = VaultSync(repo_dir=args.repo_dir)
    sync.ensure_gitignore()

    if args.action == "pull":
        result = sync.pull()
    elif args.action == "push":
        result = sync.push(args.message)
    else:
        result = sync.status()

    print(f"Status: {result['status']}")
    print(result.get("output", ""))
