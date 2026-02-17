import shutil
import pytest
from pathlib import Path

import main


@pytest.fixture(autouse=True)
def test_vault(tmp_path, monkeypatch):
    """Create a temporary vault structure for each test."""
    vault = tmp_path / "AI_Employee_Vault"
    inbox = vault / "Inbox"
    needs_action = vault / "Needs_Action"
    done = vault / "Done"
    logs = vault / "System_Logs.md"
    dashboard = vault / "Dashboard.md"

    inbox.mkdir(parents=True)
    needs_action.mkdir(parents=True)
    done.mkdir(parents=True)
    logs.write_text("# System Logs\n\n", encoding="utf-8")
    dashboard.write_text("# Dashboard\n", encoding="utf-8")

    monkeypatch.setattr(main, "VAULT", vault)
    monkeypatch.setattr(main, "INBOX", inbox)
    monkeypatch.setattr(main, "NEEDS_ACTION", needs_action)
    monkeypatch.setattr(main, "DONE", done)
    monkeypatch.setattr(main, "SYSTEM_LOGS", logs)
    monkeypatch.setattr(main, "DASHBOARD", dashboard)

    return {
        "vault": vault,
        "inbox": inbox,
        "needs_action": needs_action,
        "done": done,
        "logs": logs,
        "dashboard": dashboard,
    }


# ── Folder Structure Tests ──────────────────────────────────


class TestFolderStructure:
    def test_inbox_exists(self, test_vault):
        assert test_vault["inbox"].is_dir()

    def test_needs_action_exists(self, test_vault):
        assert test_vault["needs_action"].is_dir()

    def test_done_exists(self, test_vault):
        assert test_vault["done"].is_dir()

    def test_system_logs_exists(self, test_vault):
        assert test_vault["logs"].is_file()

    def test_dashboard_exists(self, test_vault):
        assert test_vault["dashboard"].is_file()


# ── classify_task Tests ─────────────────────────────────────


class TestClassifyTask:
    def test_urgent_returns_high(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is urgent please handle", encoding="utf-8")
        result = main.classify_task(f)
        assert result == "High"

    def test_soon_returns_medium(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Please do this soon", encoding="utf-8")
        result = main.classify_task(f)
        assert result == "Medium"

    def test_normal_returns_low(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Just a regular note", encoding="utf-8")
        result = main.classify_task(f)
        assert result == "Low"

    def test_urgent_takes_priority_over_soon(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is urgent and needed soon", encoding="utf-8")
        result = main.classify_task(f)
        assert result == "High"

    def test_case_insensitive_urgent(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is URGENT", encoding="utf-8")
        result = main.classify_task(f)
        assert result == "High"

    def test_case_insensitive_soon(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Do this SOON", encoding="utf-8")
        result = main.classify_task(f)
        assert result == "Medium"

    def test_appends_urgency_to_file(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is urgent", encoding="utf-8")
        main.classify_task(f)
        content = f.read_text(encoding="utf-8")
        assert "Urgency: High" in content

    def test_empty_file_returns_low(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("", encoding="utf-8")
        result = main.classify_task(f)
        assert result == "Low"

    def test_logs_classification(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("urgent", encoding="utf-8")
        main.classify_task(f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Classified: task.txt" in logs
        assert "Urgency: High" in logs


# ── move_to_done Tests ──────────────────────────────────────


class TestMoveToDone:
    def test_file_moves_to_done(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("content\nUrgency: Low\n", encoding="utf-8")
        main.move_to_done(f)
        assert not f.exists()
        assert (test_vault["done"] / "task.txt").exists()

    def test_file_content_preserved(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        original = "original content\nUrgency: High\n"
        f.write_text(original, encoding="utf-8")
        main.move_to_done(f)
        done_content = (test_vault["done"] / "task.txt").read_text(encoding="utf-8")
        assert done_content == original

    def test_duplicate_name_gets_timestamp(self, test_vault):
        existing = test_vault["done"] / "task.txt"
        existing.write_text("old\nUrgency: Low\n", encoding="utf-8")

        f = test_vault["needs_action"] / "task.txt"
        f.write_text("new\nUrgency: High\n", encoding="utf-8")
        main.move_to_done(f)

        done_files = list(test_vault["done"].iterdir())
        assert len(done_files) == 2

    def test_logs_completion(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("content\nUrgency: Low\n", encoding="utf-8")
        main.move_to_done(f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Task completed: task.txt" in logs


# ── log_entry Tests ─────────────────────────────────────────


class TestLogEntry:
    def test_appends_to_log_file(self, test_vault):
        main.log_entry("Test message")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Test message" in logs

    def test_includes_timestamp(self, test_vault):
        main.log_entry("Test message")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        # Timestamp format: [YYYY-MM-DD HH:MM]
        assert "[20" in logs

    def test_multiple_entries_append(self, test_vault):
        main.log_entry("First")
        main.log_entry("Second")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "First" in logs
        assert "Second" in logs


# ── update_dashboard Tests ──────────────────────────────────


class TestUpdateDashboard:
    def test_dashboard_shows_zero_when_empty(self, test_vault):
        main.update_dashboard()
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "| Done | 0 |" in content
        assert "Total Completed** | 0" in content

    def test_dashboard_counts_done_files(self, test_vault):
        (test_vault["done"] / "a.txt").write_text("A\nUrgency: High\n", encoding="utf-8")
        (test_vault["done"] / "b.txt").write_text("B\nUrgency: Low\n", encoding="utf-8")
        main.update_dashboard()
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "| Done | 2 |" in content
        assert "Total Completed** | 2" in content

    def test_dashboard_lists_completed_tasks(self, test_vault):
        (test_vault["done"] / "report.txt").write_text("data\nUrgency: High\n", encoding="utf-8")
        main.update_dashboard()
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "report.txt" in content
        assert "High" in content

    def test_dashboard_shows_online_status(self, test_vault):
        main.update_dashboard()
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "ONLINE" in content

    def test_dashboard_shows_last_updated(self, test_vault):
        main.update_dashboard()
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "Last Updated" in content
        assert "20" in content  # Year prefix


# ── Full Pipeline Tests ─────────────────────────────────────


class TestFullPipeline:
    def test_inbox_to_done_pipeline(self, test_vault):
        """Simulate the full flow: file in Needs_Action → classify → move to Done."""
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is urgent", encoding="utf-8")

        main.classify_task(f)
        main.move_to_done(f)

        assert not f.exists()
        done_file = test_vault["done"] / "task.txt"
        assert done_file.exists()
        content = done_file.read_text(encoding="utf-8")
        assert "Urgency: High" in content

    def test_multiple_files_pipeline(self, test_vault):
        """Process three files with different urgencies."""
        files = {
            "urgent.txt": ("This is urgent", "High"),
            "soon.txt": ("Do this soon", "Medium"),
            "normal.txt": ("Just a note", "Low"),
        }

        for name, (text, _) in files.items():
            f = test_vault["needs_action"] / name
            f.write_text(text, encoding="utf-8")
            main.classify_task(f)
            main.move_to_done(f)

        done_files = {f.name for f in test_vault["done"].iterdir()}
        assert done_files == {"urgent.txt", "soon.txt", "normal.txt"}

        dashboard = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "Total Completed** | 3" in dashboard

    def test_logs_capture_full_pipeline(self, test_vault):
        """Verify all three log entries appear for one file."""
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("urgent task", encoding="utf-8")

        main.classify_task(f)
        main.move_to_done(f)

        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Classified: task.txt" in logs
        assert "Task completed: task.txt" in logs
        assert "Dashboard updated" in logs
