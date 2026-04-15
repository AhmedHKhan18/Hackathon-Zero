"""
Base Watcher — Template for all AI Employee watchers.

Each watcher monitors an external source (Gmail, LinkedIn, filesystem)
and creates actionable .md files in the Needs_Action folder for Claude to process.
"""

import time
import logging
from pathlib import Path
from abc import ABC, abstractmethod
from datetime import datetime


class BaseWatcher(ABC):
    """Abstract base class for all watcher scripts."""

    def __init__(self, vault_path: str, check_interval: int = 60):
        self.vault_path = Path(vault_path)
        self.needs_action = self.vault_path / "Needs_Action"
        self.logs_dir = self.vault_path / "Logs"
        self.check_interval = check_interval
        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logging()

    def _setup_logging(self):
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        )
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log_to_vault(self, action: str, details: str, status: str = "success"):
        """Write a JSON audit log entry to the Logs/ folder."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{today}.json"

        import json

        entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action,
            "actor": self.__class__.__name__,
            "details": details,
            "result": status,
        }

        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                entries = []

        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    @abstractmethod
    def check_for_updates(self) -> list:
        """Return list of new items to process."""
        pass

    @abstractmethod
    def create_action_file(self, item) -> Path:
        """Create .md file in Needs_Action folder."""
        pass

    def run(self):
        """Main loop — poll for updates and create action files."""
        self.logger.info(f"Starting {self.__class__.__name__}")
        self.log_to_vault("watcher_start", f"{self.__class__.__name__} started")

        while True:
            try:
                items = self.check_for_updates()
                for item in items:
                    filepath = self.create_action_file(item)
                    self.logger.info(f"Action file created: {filepath.name}")
                    self.log_to_vault(
                        "action_file_created",
                        f"Created {filepath.name}",
                    )
            except KeyboardInterrupt:
                self.logger.info("Watcher stopped by user.")
                self.log_to_vault("watcher_stop", "Stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error: {e}")
                self.log_to_vault("watcher_error", str(e), status="error")
            time.sleep(self.check_interval)
