"""
Retry Handler — Error recovery with exponential backoff and circuit breaker.

Provides:
- RetryHandler class with configurable retry decorator
- Circuit breaker pattern to stop calling failing services
- Graceful degradation (queue locally when service is down)
- Error logging to Logs/errors/ as JSON

Gold Tier — Phase 1: Error Recovery Foundation.
"""

import json
import time
import functools
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger("RetryHandler")


class CircuitBreaker:
    """Circuit breaker to stop calling failing services."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def record_success(self):
        self.failure_count = 0
        self.state = self.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

    def can_execute(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = self.HALF_OPEN
                return True
            return False
        # HALF_OPEN — allow one attempt
        return True

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


class RetryHandler:
    """Handles retries with exponential backoff, circuit breakers, and error logging."""

    def __init__(self, vault_path: str | Path = None, max_retries: int = 3,
                 base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.vault_path = Path(vault_path) if vault_path else None
        self.circuit_breakers: dict[str, CircuitBreaker] = defaultdict(CircuitBreaker)
        self.error_queue: list[dict] = []
        self.stats = {"total_retries": 0, "total_failures": 0, "total_successes": 0}

    def _get_errors_dir(self) -> Path | None:
        if self.vault_path:
            errors_dir = self.vault_path / "Logs" / "errors"
            errors_dir.mkdir(parents=True, exist_ok=True)
            return errors_dir
        return None

    def log_error(self, service: str, error: Exception, context: dict = None):
        """Log an error to Logs/errors/ as JSON."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "service": service,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
        }

        errors_dir = self._get_errors_dir()
        if errors_dir:
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = errors_dir / f"{today}_errors.json"
            entries = []
            if log_file.exists():
                try:
                    entries = json.loads(log_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, ValueError):
                    entries = []
            entries.append(entry)
            log_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")

        logger.error(f"[{service}] {type(error).__name__}: {error}")

    def queue_for_retry(self, service: str, task: dict):
        """Queue a failed task for later retry."""
        self.error_queue.append({
            "service": service,
            "task": task,
            "queued_at": datetime.now().isoformat(),
            "retry_count": 0,
        })

    def get_pending_retries(self) -> list[dict]:
        return list(self.error_queue)

    def clear_completed(self):
        self.error_queue = [q for q in self.error_queue if q.get("status") != "completed"]

    def execute_with_retry(self, func, *args, service_name: str = "default", **kwargs):
        """Execute a function with exponential backoff retry."""
        breaker = self.circuit_breakers[service_name]

        if not breaker.can_execute():
            logger.warning(f"Circuit breaker OPEN for {service_name}, skipping")
            return {"status": "circuit_open", "service": service_name}

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                self.stats["total_successes"] += 1
                return result
            except Exception as e:
                last_error = e
                self.stats["total_retries"] += 1

                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    logger.info(f"Retry {attempt + 1}/{self.max_retries} for {service_name} in {delay:.1f}s")
                    time.sleep(delay)

        # All retries exhausted
        breaker.record_failure()
        self.stats["total_failures"] += 1
        self.log_error(service_name, last_error, {"attempts": self.max_retries + 1})
        return {"status": "failed", "error": str(last_error), "service": service_name}

    def retry_decorator(self, service_name: str = "default"):
        """Decorator for automatic retry with exponential backoff."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return self.execute_with_retry(func, *args, service_name=service_name, **kwargs)
            return wrapper
        return decorator

    def get_stats(self) -> dict:
        breaker_stats = {}
        for name, breaker in self.circuit_breakers.items():
            breaker_stats[name] = breaker.to_dict()

        return {
            **self.stats,
            "pending_retries": len(self.error_queue),
            "circuit_breakers": breaker_stats,
        }
