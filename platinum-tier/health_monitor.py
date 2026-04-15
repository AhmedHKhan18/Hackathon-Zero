"""
Health Monitor — Cloud agent health monitoring for Platinum Tier.

Runs as a lightweight sidecar on the Cloud VM alongside cloud_agent.py.
Provides:
  1. HTTP health endpoint (GET /health) for uptime monitors like UptimeRobot
  2. Periodic heartbeat writes to /Signals/health.md in the vault
  3. Process watchdog: restarts cloud_agent.py if it crashes
  4. Alert file writes to /Signals/alert.md when issues are detected

Usage (on cloud VM):
    python health_monitor.py --vault-path /home/ubuntu/platinum-tier/AI_Employee_Vault
    python health_monitor.py --vault-path /path/to/vault --port 8080 --no-watchdog

Systemd: see cloud_deploy/health-monitor.service
"""

import os
import sys
import time
import logging
import argparse
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HealthMonitor] %(levelname)s: %(message)s",
)
logger = logging.getLogger("HealthMonitor")

# Health state shared between HTTP handler and watchdog thread
_health_state = {
    "status": "starting",
    "agent_pid": None,
    "last_heartbeat": None,
    "uptime_start": datetime.now().isoformat(),
    "restarts": 0,
}
_state_lock = threading.Lock()


# ---------------------------------------------------------------------------
# HTTP Health Endpoint
# ---------------------------------------------------------------------------

class HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for health checks."""

    def do_GET(self):
        if self.path in ("/health", "/", "/status"):
            self._respond_health()
        else:
            self.send_response(404)
            self.end_headers()

    def _respond_health(self):
        with _state_lock:
            state = dict(_health_state)

        status_code = 200 if state["status"] == "online" else 503
        body = (
            f"status: {state['status']}\n"
            f"agent_pid: {state['agent_pid']}\n"
            f"last_heartbeat: {state['last_heartbeat']}\n"
            f"uptime_since: {state['uptime_start']}\n"
            f"restarts: {state['restarts']}\n"
        ).encode()

        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Suppress access log spam


def run_http_server(port: int):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Health HTTP endpoint listening on :{port}")
    server.serve_forever()


# ---------------------------------------------------------------------------
# Heartbeat Writer
# ---------------------------------------------------------------------------

def write_heartbeat(vault_path: Path):
    """Write health heartbeat to /Signals/health.md."""
    signals_dir = vault_path / "Signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    health_path = signals_dir / "health.md"

    with _state_lock:
        status = _health_state["status"]
        pid = _health_state["agent_pid"]
        restarts = _health_state["restarts"]

    now = datetime.now()
    health_path.write_text(
        f"---\nagent_id: cloud-agent\nhostname: {os.uname().nodename if hasattr(os, 'uname') else 'unknown'}\n"
        f"last_heartbeat: {now.isoformat()}\nstatus: {status}\n"
        f"pid: {pid}\nrestarts: {restarts}\n---\n\n"
        f"# Cloud Agent Health Monitor\n\n"
        f"| Field | Value |\n|---|---|\n"
        f"| **Status** | {status.upper()} |\n"
        f"| **Agent PID** | {pid} |\n"
        f"| **Restarts** | {restarts} |\n"
        f"| **Last Heartbeat** | {now.strftime('%Y-%m-%d %H:%M:%S')} |\n"
        f"| **Uptime Since** | {_health_state['uptime_start']} |\n",
        encoding="utf-8",
    )
    with _state_lock:
        _health_state["last_heartbeat"] = now.isoformat()


def write_alert(vault_path: Path, message: str):
    """Write alert to /Signals/alert.md for Local agent to see."""
    signals_dir = vault_path / "Signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    alert_path = signals_dir / "alert.md"
    timestamp = datetime.now().isoformat()
    alert_path.write_text(
        f"---\ntype: alert\ntimestamp: {timestamp}\n---\n\n"
        f"# Cloud Agent Alert\n\n{message}\n\nTimestamp: {timestamp}\n",
        encoding="utf-8",
    )
    logger.warning(f"[Alert] {message}")


# ---------------------------------------------------------------------------
# Process Watchdog
# ---------------------------------------------------------------------------

class CloudAgentWatchdog:
    """Start and restart cloud_agent.py if it crashes."""

    def __init__(self, cloud_agent_cmd: list, vault_path: Path, max_restarts: int = 10):
        self.cmd = cloud_agent_cmd
        self.vault_path = vault_path
        self.max_restarts = max_restarts
        self.proc = None

    def run(self):
        restarts = 0
        while restarts <= self.max_restarts:
            logger.info(f"[Watchdog] Starting cloud_agent (attempt {restarts + 1})")
            self.proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            with _state_lock:
                _health_state["agent_pid"] = self.proc.pid
                _health_state["status"] = "online"

            # Stream output
            for line in self.proc.stdout:
                logger.info(f"[CloudAgent] {line.rstrip()}")

            self.proc.wait()
            exit_code = self.proc.returncode
            logger.warning(f"[Watchdog] cloud_agent exited with code {exit_code}")

            restarts += 1
            with _state_lock:
                _health_state["restarts"] = restarts
                _health_state["status"] = "restarting"
                _health_state["agent_pid"] = None

            if restarts > self.max_restarts:
                with _state_lock:
                    _health_state["status"] = "failed"
                write_alert(
                    self.vault_path,
                    f"Cloud agent crashed {restarts} times. Manual intervention required. "
                    f"Last exit code: {exit_code}",
                )
                break

            if restarts <= self.max_restarts:
                write_alert(
                    self.vault_path,
                    f"Cloud agent restarting (attempt {restarts}/{self.max_restarts}). "
                    f"Exit code was: {exit_code}",
                )
                backoff = min(30 * restarts, 300)
                logger.info(f"[Watchdog] Waiting {backoff}s before restart...")
                time.sleep(backoff)


# ---------------------------------------------------------------------------
# Heartbeat Loop
# ---------------------------------------------------------------------------

def heartbeat_loop(vault_path: Path, interval_seconds: int = 120):
    """Write heartbeat every interval_seconds."""
    while True:
        try:
            write_heartbeat(vault_path)
        except Exception as e:
            logger.error(f"[Heartbeat] Failed: {e}")
        time.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AI Employee Cloud Health Monitor")
    parser.add_argument(
        "--vault-path",
        default=os.environ.get("VAULT_PATH", "AI_Employee_Vault"),
        help="Path to the AI Employee Vault",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HEALTH_PORT", "8080")),
        help="HTTP health endpoint port",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=120,
        help="Heartbeat write interval in seconds (default: 120)",
    )
    parser.add_argument(
        "--no-watchdog",
        action="store_true",
        help="Skip process watchdog (just run health endpoint + heartbeat)",
    )
    parser.add_argument(
        "--cloud-agent-cmd",
        default="python cloud_agent.py",
        help="Command to start cloud_agent.py",
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=10,
        help="Max cloud_agent restart attempts before giving up",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault_path)
    vault_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Health Monitor starting — vault: {vault_path}, port: {args.port}")

    # Thread 1: HTTP health endpoint
    http_thread = threading.Thread(
        target=run_http_server,
        args=(args.port,),
        daemon=True,
        name="HealthHTTP",
    )
    http_thread.start()

    # Thread 2: Heartbeat writer
    hb_thread = threading.Thread(
        target=heartbeat_loop,
        args=(vault_path, args.heartbeat_interval),
        daemon=True,
        name="Heartbeat",
    )
    hb_thread.start()

    with _state_lock:
        _health_state["status"] = "online"

    # Thread 3 (optional): Process watchdog
    if not args.no_watchdog:
        cmd = args.cloud_agent_cmd.split()
        watchdog = CloudAgentWatchdog(
            cloud_agent_cmd=cmd,
            vault_path=vault_path,
            max_restarts=args.max_restarts,
        )
        watchdog_thread = threading.Thread(
            target=watchdog.run,
            daemon=False,
            name="Watchdog",
        )
        watchdog_thread.start()
        logger.info("Watchdog started — monitoring cloud_agent.py")
        watchdog_thread.join()
    else:
        logger.info("Running in no-watchdog mode (health endpoint + heartbeat only)")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Health Monitor shutting down")


if __name__ == "__main__":
    main()
