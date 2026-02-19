"""
Scheduler — Basic task scheduling for the AI Employee.

Handles timed operations:
- Daily briefing generation (8:00 AM)
- LinkedIn post scheduling (configurable)
- Periodic vault health checks
- Weekly business audit

Uses Python's sched module (no external dependencies).
Can also generate Windows Task Scheduler XML for persistent scheduling.

Usage:
    python scheduler.py [--vault-path PATH]
"""

import os
import json
import sched
import time
import threading
import argparse
from pathlib import Path
from datetime import datetime, timedelta

from agent_skills import (
    SkillRegistry,
    UpdateDashboardSkill,
    VaultWatcherSkill,
    CEOBriefingSkill,
    LinkedInAutoPostSkill,
    AuditLogSkill,
)


class AIEmployeeScheduler:
    """Manages scheduled tasks for the AI Employee."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.running = False

        vault_paths = {
            "vault": self.vault_path,
            "inbox": self.vault_path / "Inbox",
            "needs_action": self.vault_path / "Needs_Action",
            "done": self.vault_path / "Done",
            "system_logs": self.vault_path / "System_Logs.md",
            "dashboard": self.vault_path / "Dashboard.md",
            "plans": self.vault_path / "Plans",
            "pending_approval": self.vault_path / "Pending_Approval",
            "approved": self.vault_path / "Approved",
            "rejected": self.vault_path / "Rejected",
            "logs_dir": self.vault_path / "Logs",
        }

        self.registry = SkillRegistry(vault_paths)
        self.registry.register(UpdateDashboardSkill)
        self.registry.register(VaultWatcherSkill)
        self.registry.register(CEOBriefingSkill)
        self.registry.register(LinkedInAutoPostSkill)
        self.registry.register(AuditLogSkill)

        self.schedules = []

    def add_recurring(self, name: str, interval_seconds: int, callback):
        """Add a recurring scheduled task."""
        self.schedules.append({
            "name": name,
            "interval": interval_seconds,
            "callback": callback,
            "next_run": time.time() + interval_seconds,
        })

    def daily_briefing(self):
        """Generate a daily CEO briefing."""
        print(f"[{datetime.now().strftime('%H:%M')}] Generating daily briefing...")
        self.registry.run("ceo_briefing")
        self.registry.run("update_dashboard")

    def health_check(self):
        """Run vault health check."""
        result = self.registry.run("vault_watcher")
        status = result.get("status", "UNKNOWN")
        print(f"[{datetime.now().strftime('%H:%M')}] Health check: {status}")

    def linkedin_schedule_check(self):
        """Check for scheduled LinkedIn posts ready to go."""
        post_dir = self.vault_path / "Inbox" / "linkedin_posts"
        if not post_dir.exists():
            return

        pending = [f for f in post_dir.iterdir() if f.is_file()]
        if pending:
            print(f"[{datetime.now().strftime('%H:%M')}] {len(pending)} LinkedIn posts queued")

    def setup_default_schedule(self):
        """Configure the default schedule."""
        # Health check every 5 minutes
        self.add_recurring("Health Check", 300, self.health_check)

        # Daily briefing every 24 hours
        self.add_recurring("Daily Briefing", 86400, self.daily_briefing)

        # LinkedIn check every 30 minutes
        self.add_recurring("LinkedIn Schedule", 1800, self.linkedin_schedule_check)

    def generate_task_scheduler_xml(self, output_path: str = None):
        """Generate Windows Task Scheduler XML for persistent scheduling."""
        if output_path is None:
            output_path = str(self.vault_path.parent / "scheduled_tasks.xml")

        python_path = os.sys.executable
        script_path = str(Path(__file__).parent / "orchestrator.py")

        xml_content = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>AI Employee Orchestrator - Runs the AI Employee system</Description>
    <Author>AI Employee</Author>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T08:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python_path}</Command>
      <Arguments>{script_path}</Arguments>
      <WorkingDirectory>{str(Path(__file__).parent)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
        Path(output_path).write_text(xml_content, encoding="utf-16")
        print(f"Task Scheduler XML generated: {output_path}")
        print("Import with: schtasks /create /tn \"AI_Employee\" /xml scheduled_tasks.xml")
        return output_path

    def run(self):
        """Run the scheduler loop."""
        self.running = True
        self.setup_default_schedule()

        print("=" * 50)
        print("  AI Employee — Scheduler")
        print(f"  Vault: {self.vault_path}")
        print(f"  Scheduled tasks: {len(self.schedules)}")
        for s in self.schedules:
            print(f"    - {s['name']}: every {s['interval']}s")
        print("=" * 50)

        try:
            while self.running:
                now = time.time()
                for s in self.schedules:
                    if now >= s["next_run"]:
                        try:
                            s["callback"]()
                        except Exception as e:
                            print(f"Error in {s['name']}: {e}")
                        s["next_run"] = now + s["interval"]
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            print("\nScheduler stopped.")


def main():
    parser = argparse.ArgumentParser(description="AI Employee Scheduler")
    parser.add_argument(
        "--vault-path",
        default=str(Path(__file__).parent / "AI_Employee_Vault"),
        help="Path to the Obsidian vault",
    )
    parser.add_argument(
        "--generate-xml",
        action="store_true",
        help="Generate Windows Task Scheduler XML and exit",
    )
    args = parser.parse_args()

    scheduler = AIEmployeeScheduler(args.vault_path)

    if args.generate_xml:
        scheduler.generate_task_scheduler_xml()
    else:
        scheduler.run()


if __name__ == "__main__":
    main()
