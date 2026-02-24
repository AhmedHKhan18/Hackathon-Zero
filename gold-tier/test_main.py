"""
Tests for AI Employee Vault — Gold Tier.

Covers all Bronze + Silver + Gold tier skills, MCP servers, Ralph loop,
retry handler, and pipeline functionality.
"""

import json
import shutil
import pytest
from pathlib import Path

import main
from agent_skills import (
    SkillRegistry,
    ClassifySkill,
    MoveToeDoneSkill,
    UpdateDashboardSkill,
    TaskPlannerSkill,
    VaultFileManagerSkill,
    VaultWatcherSkill,
    HumanApprovalSkill,
    GmailSendSkill,
    LinkedInPostSkill,
    WhatsAppReplySkill,
    PlanCreatorSkill,
    ApprovalWatcherSkill,
    SchedulerSkill,
    CEOBriefingSkill,
    LinkedInAutoPostSkill,
    AuditLogSkill,
    OdooAccountingSkill,
    FacebookPostSkill,
    InstagramPostSkill,
    TwitterPostSkill,
    SocialMediaSummarySkill,
    WeeklyBusinessAuditSkill,
    ErrorRecoverySkill,
)
from retry_handler import RetryHandler, CircuitBreaker
from ralph_loop import RalphWiggumLoop

ALL_SKILLS = [
    ClassifySkill,
    MoveToeDoneSkill,
    UpdateDashboardSkill,
    TaskPlannerSkill,
    VaultFileManagerSkill,
    VaultWatcherSkill,
    HumanApprovalSkill,
    GmailSendSkill,
    LinkedInPostSkill,
    WhatsAppReplySkill,
    PlanCreatorSkill,
    ApprovalWatcherSkill,
    SchedulerSkill,
    CEOBriefingSkill,
    LinkedInAutoPostSkill,
    AuditLogSkill,
    OdooAccountingSkill,
    FacebookPostSkill,
    InstagramPostSkill,
    TwitterPostSkill,
    SocialMediaSummarySkill,
    WeeklyBusinessAuditSkill,
    ErrorRecoverySkill,
]


@pytest.fixture(autouse=True)
def test_vault(tmp_path, monkeypatch):
    """Create a temporary vault structure for each test."""
    vault = tmp_path / "AI_Employee_Vault"
    inbox = vault / "Inbox"
    needs_action = vault / "Needs_Action"
    done = vault / "Done"
    plans = vault / "Plans"
    pending_approval = vault / "Pending_Approval"
    approved = vault / "Approved"
    rejected = vault / "Rejected"
    logs_dir = vault / "Logs"
    logs = vault / "System_Logs.md"
    dashboard = vault / "Dashboard.md"

    for d in [inbox, needs_action, done, plans, pending_approval, approved, rejected, logs_dir]:
        d.mkdir(parents=True)

    logs.write_text("# System Logs\n\n", encoding="utf-8")
    dashboard.write_text("# Dashboard\n", encoding="utf-8")

    vault_paths = {
        "vault": vault,
        "inbox": inbox,
        "needs_action": needs_action,
        "done": done,
        "system_logs": logs,
        "dashboard": dashboard,
        "plans": plans,
        "pending_approval": pending_approval,
        "approved": approved,
        "rejected": rejected,
        "logs_dir": logs_dir,
    }

    monkeypatch.setattr(main, "VAULT", vault)
    monkeypatch.setattr(main, "INBOX", inbox)
    monkeypatch.setattr(main, "NEEDS_ACTION", needs_action)
    monkeypatch.setattr(main, "DONE", done)
    monkeypatch.setattr(main, "PLANS", plans)
    monkeypatch.setattr(main, "PENDING_APPROVAL", pending_approval)
    monkeypatch.setattr(main, "APPROVED", approved)
    monkeypatch.setattr(main, "REJECTED", rejected)
    monkeypatch.setattr(main, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(main, "SYSTEM_LOGS", logs)
    monkeypatch.setattr(main, "DASHBOARD", dashboard)

    # Create a fresh registry with all skills
    test_registry = SkillRegistry(vault_paths)
    for skill in ALL_SKILLS:
        test_registry.register(skill)
    monkeypatch.setattr(main, "registry", test_registry)

    return {
        "vault": vault,
        "inbox": inbox,
        "needs_action": needs_action,
        "done": done,
        "plans": plans,
        "pending_approval": pending_approval,
        "approved": approved,
        "rejected": rejected,
        "logs_dir": logs_dir,
        "logs": logs,
        "dashboard": dashboard,
        "registry": test_registry,
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

    def test_plans_exists(self, test_vault):
        assert test_vault["plans"].is_dir()

    def test_pending_approval_exists(self, test_vault):
        assert test_vault["pending_approval"].is_dir()

    def test_approved_exists(self, test_vault):
        assert test_vault["approved"].is_dir()

    def test_rejected_exists(self, test_vault):
        assert test_vault["rejected"].is_dir()

    def test_logs_dir_exists(self, test_vault):
        assert test_vault["logs_dir"].is_dir()


# ── Agent Skill Registry Tests ──────────────────────────────


class TestSkillRegistry:
    def test_registry_has_all_skills(self, test_vault):
        skills = test_vault["registry"].list_skills()
        assert len(skills) == 23

    def test_registry_has_bronze_skills(self, test_vault):
        skills = test_vault["registry"].list_skills()
        bronze_skills = [
            "classify", "move_to_done", "update_dashboard", "task_planner",
            "vault_file_manager", "vault_watcher", "human_approval",
            "gmail_send", "linkedin_post",
        ]
        for s in bronze_skills:
            assert s in skills, f"Missing bronze skill: {s}"

    def test_registry_has_whatsapp_reply(self, test_vault):
        assert "whatsapp_reply" in test_vault["registry"].list_skills()

    def test_registry_has_silver_skills(self, test_vault):
        skills = test_vault["registry"].list_skills()
        silver_skills = [
            "whatsapp_reply", "plan_creator", "approval_watcher", "scheduler",
            "ceo_briefing", "linkedin_auto_post", "audit_log",
        ]
        for s in silver_skills:
            assert s in skills, f"Missing silver skill: {s}"

    def test_registry_has_gold_skills(self, test_vault):
        skills = test_vault["registry"].list_skills()
        gold_skills = [
            "odoo_accounting", "facebook_post", "instagram_post", "twitter_post",
            "social_media_summary", "weekly_business_audit", "error_recovery",
        ]
        for s in gold_skills:
            assert s in skills, f"Missing gold skill: {s}"

    def test_get_skill_by_name(self, test_vault):
        skill = test_vault["registry"].get("classify")
        assert skill.name == "classify"

    def test_all_skills_have_descriptions(self, test_vault):
        for name in test_vault["registry"].list_skills():
            skill = test_vault["registry"].get(name)
            assert len(skill.description) > 0, f"{name} has no description"


# ── ClassifySkill Tests ─────────────────────────────────────


class TestClassifySkill:
    def test_urgent_returns_high(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is urgent please handle", encoding="utf-8")
        result = test_vault["registry"].run("classify", f)
        assert result["urgency"] == "High"

    def test_soon_returns_medium(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Please do this soon", encoding="utf-8")
        result = test_vault["registry"].run("classify", f)
        assert result["urgency"] == "Medium"

    def test_normal_returns_low(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Just a regular note", encoding="utf-8")
        result = test_vault["registry"].run("classify", f)
        assert result["urgency"] == "Low"

    def test_urgent_takes_priority_over_soon(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is urgent and needed soon", encoding="utf-8")
        result = test_vault["registry"].run("classify", f)
        assert result["urgency"] == "High"

    def test_case_insensitive_urgent(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is URGENT", encoding="utf-8")
        result = test_vault["registry"].run("classify", f)
        assert result["urgency"] == "High"

    def test_case_insensitive_soon(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Do this SOON", encoding="utf-8")
        result = test_vault["registry"].run("classify", f)
        assert result["urgency"] == "Medium"

    def test_appends_urgency_to_file(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is urgent", encoding="utf-8")
        test_vault["registry"].run("classify", f)
        content = f.read_text(encoding="utf-8")
        assert "Urgency: High" in content

    def test_empty_file_returns_low(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("", encoding="utf-8")
        result = test_vault["registry"].run("classify", f)
        assert result["urgency"] == "Low"

    def test_logs_classification(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("urgent", encoding="utf-8")
        test_vault["registry"].run("classify", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Classified: task.txt" in logs
        assert "Urgency: High" in logs


# ── MoveToDoneSkill Tests ───────────────────────────────────


class TestMoveToDoneSkill:
    def test_file_moves_to_done(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("content\nUrgency: Low\n", encoding="utf-8")
        test_vault["registry"].run("move_to_done", f)
        assert not f.exists()
        assert (test_vault["done"] / "task.txt").exists()

    def test_file_content_preserved(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        original = "original content\nUrgency: High\n"
        f.write_text(original, encoding="utf-8")
        test_vault["registry"].run("move_to_done", f)
        done_content = (test_vault["done"] / "task.txt").read_text(encoding="utf-8")
        assert done_content == original

    def test_duplicate_name_gets_timestamp(self, test_vault):
        existing = test_vault["done"] / "task.txt"
        existing.write_text("old\nUrgency: Low\n", encoding="utf-8")
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("new\nUrgency: High\n", encoding="utf-8")
        test_vault["registry"].run("move_to_done", f)
        done_files = list(test_vault["done"].iterdir())
        assert len(done_files) == 2

    def test_logs_completion(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("content\nUrgency: Low\n", encoding="utf-8")
        test_vault["registry"].run("move_to_done", f)
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
        assert "[20" in logs

    def test_multiple_entries_append(self, test_vault):
        main.log_entry("First")
        main.log_entry("Second")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "First" in logs
        assert "Second" in logs


# ── UpdateDashboardSkill Tests ──────────────────────────────


class TestUpdateDashboardSkill:
    def test_dashboard_shows_zero_when_empty(self, test_vault):
        test_vault["registry"].run("update_dashboard")
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "| Done | 0 |" in content
        assert "Total Completed** | 0" in content

    def test_dashboard_counts_done_files(self, test_vault):
        (test_vault["done"] / "a.txt").write_text("A\nUrgency: High\n", encoding="utf-8")
        (test_vault["done"] / "b.txt").write_text("B\nUrgency: Low\n", encoding="utf-8")
        test_vault["registry"].run("update_dashboard")
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "| Done | 2 |" in content
        assert "Total Completed** | 2" in content

    def test_dashboard_lists_completed_tasks(self, test_vault):
        (test_vault["done"] / "report.txt").write_text("data\nUrgency: High\n", encoding="utf-8")
        test_vault["registry"].run("update_dashboard")
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "report.txt" in content
        assert "High" in content

    def test_dashboard_shows_online_status(self, test_vault):
        test_vault["registry"].run("update_dashboard")
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "ONLINE" in content

    def test_dashboard_shows_gold_tier(self, test_vault):
        test_vault["registry"].run("update_dashboard")
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "Gold" in content

    def test_dashboard_shows_approval_queue(self, test_vault):
        (test_vault["pending_approval"] / "req.md").write_text("approval", encoding="utf-8")
        test_vault["registry"].run("update_dashboard")
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "Pending Approval | 1" in content

    def test_dashboard_shows_plans_count(self, test_vault):
        (test_vault["plans"] / "plan.md").write_text("plan", encoding="utf-8")
        test_vault["registry"].run("update_dashboard")
        content = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "Plans | 1" in content


# ── TaskPlannerSkill Tests ──────────────────────────────────


class TestTaskPlannerSkill:
    def test_creates_action_plan(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Review the report\nSend feedback\nClose ticket", encoding="utf-8")
        result = test_vault["registry"].run("task_planner", f)
        assert result["step_count"] == 3

    def test_plan_appended_to_file(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Do the thing", encoding="utf-8")
        test_vault["registry"].run("task_planner", f)
        content = f.read_text(encoding="utf-8")
        assert "--- Action Plan ---" in content
        assert "Step 1:" in content

    def test_skips_urgency_lines(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Fix the bug\nUrgency: High", encoding="utf-8")
        result = test_vault["registry"].run("task_planner", f)
        assert result["step_count"] == 1
        content = f.read_text(encoding="utf-8")
        assert "Urgency:" not in result["steps"][0]

    def test_empty_file_gets_fallback_plan(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("", encoding="utf-8")
        result = test_vault["registry"].run("task_planner", f)
        assert result["step_count"] == 1
        assert "empty task" in result["steps"][0].lower()

    def test_logs_planning(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Step one\nStep two", encoding="utf-8")
        test_vault["registry"].run("task_planner", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Task planned: task.txt" in logs


# ── VaultFileManagerSkill Tests ─────────────────────────────


class TestVaultFileManagerSkill:
    def test_empty_vault_inventory(self, test_vault):
        result = test_vault["registry"].run("vault_file_manager")
        assert result["total_files"] == 0

    def test_counts_files_in_all_folders(self, test_vault):
        (test_vault["inbox"] / "a.txt").write_text("a", encoding="utf-8")
        (test_vault["needs_action"] / "b.txt").write_text("b", encoding="utf-8")
        (test_vault["done"] / "c.txt").write_text("c", encoding="utf-8")
        result = test_vault["registry"].run("vault_file_manager")
        assert result["total_files"] == 3
        assert "a.txt" in result["inventory"]["inbox"]
        assert "b.txt" in result["inventory"]["needs_action"]
        assert "c.txt" in result["inventory"]["done"]

    def test_counts_plans_and_approvals(self, test_vault):
        (test_vault["plans"] / "plan.md").write_text("plan", encoding="utf-8")
        (test_vault["pending_approval"] / "req.md").write_text("req", encoding="utf-8")
        result = test_vault["registry"].run("vault_file_manager")
        assert "plan.md" in result["inventory"]["plans"]
        assert "req.md" in result["inventory"]["pending_approval"]

    def test_logs_inventory(self, test_vault):
        test_vault["registry"].run("vault_file_manager")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Vault inventory" in logs


# ── VaultWatcherSkill Tests ─────────────────────────────────


class TestVaultWatcherSkill:
    def test_healthy_status(self, test_vault):
        result = test_vault["registry"].run("vault_watcher")
        assert result["status"] == "HEALTHY"

    def test_all_folders_healthy(self, test_vault):
        result = test_vault["registry"].run("vault_watcher")
        assert all(result["health"].values())

    def test_reports_inbox_pending_count(self, test_vault):
        (test_vault["inbox"] / "a.txt").write_text("a", encoding="utf-8")
        (test_vault["inbox"] / "b.txt").write_text("b", encoding="utf-8")
        result = test_vault["registry"].run("vault_watcher")
        assert result["inbox_pending"] == 2

    def test_logs_health_check(self, test_vault):
        test_vault["registry"].run("vault_watcher")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Vault health check" in logs

    def test_checks_silver_tier_folders(self, test_vault):
        result = test_vault["registry"].run("vault_watcher")
        assert "plans_exists" in result["health"]
        assert "pending_approval_exists" in result["health"]
        assert "approved_exists" in result["health"]
        assert "rejected_exists" in result["health"]


# ── HumanApprovalSkill Tests ───────────────────────────────


class TestHumanApprovalSkill:
    def test_flags_file_for_approval(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Sensitive task", encoding="utf-8")
        result = test_vault["registry"].run("human_approval", f)
        assert result["status"] == "awaiting_approval"

    def test_creates_approval_file_in_pending(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Send email to client", encoding="utf-8")
        result = test_vault["registry"].run("human_approval", f)
        approval_files = list(test_vault["pending_approval"].iterdir())
        assert len(approval_files) == 1
        assert "APPROVAL_" in approval_files[0].name

    def test_approval_file_has_action_type(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Send email to client", encoding="utf-8")
        result = test_vault["registry"].run("human_approval", f)
        assert result["action_type"] == "email_send"

    def test_approval_for_linkedin(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Post to LinkedIn about AI", encoding="utf-8")
        result = test_vault["registry"].run("human_approval", f)
        assert result["action_type"] == "linkedin_post"

    def test_approval_for_payment(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Process payment for invoice", encoding="utf-8")
        result = test_vault["registry"].run("human_approval", f)
        assert result["action_type"] == "payment"

    def test_appends_approval_tag_to_file(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Sensitive task", encoding="utf-8")
        test_vault["registry"].run("human_approval", f)
        content = f.read_text(encoding="utf-8")
        assert "AWAITING HUMAN APPROVAL" in content
        assert "PENDING REVIEW" in content

    def test_logs_approval_request(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Important", encoding="utf-8")
        test_vault["registry"].run("human_approval", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Human approval required" in logs


# ── GmailSendSkill Tests ───────────────────────────────────


class TestGmailSendSkill:
    def test_creates_email_draft_file(self, test_vault):
        f = test_vault["needs_action"] / "email_task.txt"
        f.write_text("Meeting Follow Up\nHi, just following up on our meeting.", encoding="utf-8")
        result = test_vault["registry"].run("gmail_send", f)
        draft_path = test_vault["vault"] / result["draft_file"]
        assert draft_path.exists()

    def test_draft_has_correct_subject(self, test_vault):
        f = test_vault["needs_action"] / "email_task.txt"
        f.write_text("Project Update\nHere is the latest status.", encoding="utf-8")
        result = test_vault["registry"].run("gmail_send", f)
        assert result["subject"] == "Project Update"

    def test_draft_is_valid_json(self, test_vault):
        f = test_vault["needs_action"] / "email_task.txt"
        f.write_text("Hello\nWorld", encoding="utf-8")
        result = test_vault["registry"].run("gmail_send", f)
        draft_path = test_vault["vault"] / result["draft_file"]
        data = json.loads(draft_path.read_text(encoding="utf-8"))
        assert data["status"] == "draft"
        assert data["subject"] == "Hello"
        assert "World" in data["body"]

    def test_draft_status_is_draft(self, test_vault):
        f = test_vault["needs_action"] / "email_task.txt"
        f.write_text("Test\nBody", encoding="utf-8")
        result = test_vault["registry"].run("gmail_send", f)
        assert result["status"] == "draft"

    def test_logs_draft_creation(self, test_vault):
        f = test_vault["needs_action"] / "email_task.txt"
        f.write_text("Subject\nBody", encoding="utf-8")
        test_vault["registry"].run("gmail_send", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Email draft created" in logs


# ── LinkedInPostSkill Tests ─────────────────────────────────


class TestLinkedInPostSkill:
    def test_creates_linkedin_draft_file(self, test_vault):
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("Excited to share my latest project!", encoding="utf-8")
        result = test_vault["registry"].run("linkedin_post", f)
        draft_path = test_vault["vault"] / result["draft_file"]
        assert draft_path.exists()

    def test_draft_has_char_count(self, test_vault):
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("Short post", encoding="utf-8")
        result = test_vault["registry"].run("linkedin_post", f)
        assert result["char_count"] == len("Short post")

    def test_draft_strips_urgency_metadata(self, test_vault):
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("Great news!\nUrgency: High\nMore details here", encoding="utf-8")
        result = test_vault["registry"].run("linkedin_post", f)
        draft_path = test_vault["vault"] / result["draft_file"]
        data = json.loads(draft_path.read_text(encoding="utf-8"))
        assert "Urgency:" not in data["content"]
        assert "Great news!" in data["content"]

    def test_draft_is_valid_json(self, test_vault):
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("My post content", encoding="utf-8")
        result = test_vault["registry"].run("linkedin_post", f)
        draft_path = test_vault["vault"] / result["draft_file"]
        data = json.loads(draft_path.read_text(encoding="utf-8"))
        assert data["status"] == "draft"
        assert "My post content" in data["content"]

    def test_logs_draft_creation(self, test_vault):
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("Post content", encoding="utf-8")
        test_vault["registry"].run("linkedin_post", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "LinkedIn draft created" in logs


# ── WhatsAppReplySkill Tests ─────────────────────────────────


class TestWhatsAppReplySkill:
    def test_creates_reply_draft(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "WHATSAPP_client_20260223.md"
        f.write_text(
            "---\ntype: whatsapp_message\nfrom: Client A\nphone: +1234567890\n---\n\n"
            "### Message Content\nHey, can you send me the invoice for January?\n",
            encoding="utf-8",
        )
        result = test_vault["registry"].run("whatsapp_reply", f)
        assert result["status"] == "draft"
        assert result["to"] == "Client A"

    def test_draft_file_is_valid_json(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "WHATSAPP_client_20260223.md"
        f.write_text(
            "---\nfrom: Bob\nphone: +111\n---\n\n### Message Content\nUrgent help needed\n",
            encoding="utf-8",
        )
        result = test_vault["registry"].run("whatsapp_reply", f)
        draft_path = test_vault["vault"] / result["draft_file"]
        assert draft_path.exists()
        data = json.loads(draft_path.read_text(encoding="utf-8"))
        assert data["status"] == "draft"
        assert data["to"] == "Bob"
        assert "phone" in data

    def test_extracts_message_content(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "WHATSAPP_test_20260223.md"
        f.write_text(
            "---\nfrom: Alice\nphone: +999\n---\n\n"
            "### Message Content\nPlease send the payment details ASAP\n\n"
            "## Suggested Actions\n- Reply\n",
            encoding="utf-8",
        )
        result = test_vault["registry"].run("whatsapp_reply", f)
        draft_path = test_vault["vault"] / result["draft_file"]
        data = json.loads(draft_path.read_text(encoding="utf-8"))
        assert "payment details" in data["original_message"].lower()

    def test_dry_run_mode(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "WHATSAPP_test_20260223.md"
        f.write_text("---\nfrom: Test\n---\n\n### Message Content\nHello\n", encoding="utf-8")
        result = test_vault["registry"].run("whatsapp_reply", f)
        assert result["mode"] == "dry_run"

    def test_logs_draft_creation(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "WHATSAPP_test_20260223.md"
        f.write_text("---\nfrom: Test User\n---\n\n### Message Content\nHi\n", encoding="utf-8")
        test_vault["registry"].run("whatsapp_reply", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "WhatsApp reply draft" in logs

    def test_approval_for_whatsapp(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Reply on WhatsApp to client about order", encoding="utf-8")
        result = test_vault["registry"].run("human_approval", f)
        # WhatsApp isn't a direct keyword for HumanApprovalSkill action_type detection
        # but the approval is created successfully
        assert result["status"] == "awaiting_approval"


# ── PlanCreatorSkill Tests (Silver Tier) ────────────────────


class TestPlanCreatorSkill:
    def test_creates_plan_file(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Review the report\nSend feedback", encoding="utf-8")
        result = test_vault["registry"].run("plan_creator", f)
        assert result["plan_file"].startswith("PLAN_")
        plan_files = list(test_vault["plans"].iterdir())
        assert len(plan_files) == 1

    def test_plan_has_correct_steps(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Step one\nStep two\nStep three", encoding="utf-8")
        result = test_vault["registry"].run("plan_creator", f)
        assert result["steps"] == 3

    def test_plan_detects_approval_needed(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Send invoice to client for payment", encoding="utf-8")
        result = test_vault["registry"].run("plan_creator", f)
        assert result["needs_approval"] is True
        assert result["status"] == "pending_approval"

    def test_plan_no_approval_for_simple_task(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Review the documentation", encoding="utf-8")
        result = test_vault["registry"].run("plan_creator", f)
        assert result["needs_approval"] is False
        assert result["status"] == "ready"

    def test_plan_content_has_objective(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Update the website", encoding="utf-8")
        result = test_vault["registry"].run("plan_creator", f)
        plan_file = test_vault["plans"] / result["plan_file"]
        content = plan_file.read_text(encoding="utf-8")
        assert "Objective" in content
        assert "task.txt" in content

    def test_plan_content_has_steps(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Do thing A\nDo thing B", encoding="utf-8")
        result = test_vault["registry"].run("plan_creator", f)
        plan_file = test_vault["plans"] / result["plan_file"]
        content = plan_file.read_text(encoding="utf-8")
        assert "Step 1" in content
        assert "Step 2" in content

    def test_logs_plan_creation(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Some task", encoding="utf-8")
        test_vault["registry"].run("plan_creator", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Plan created" in logs


# ── ApprovalWatcherSkill Tests ──────────────────────────────


class TestApprovalWatcherSkill:
    def test_reports_empty_queues(self, test_vault):
        result = test_vault["registry"].run("approval_watcher")
        assert result["pending_count"] == 0
        assert result["approved_count"] == 0
        assert result["rejected_count"] == 0

    def test_counts_pending_approvals(self, test_vault):
        (test_vault["pending_approval"] / "req1.md").write_text("req", encoding="utf-8")
        (test_vault["pending_approval"] / "req2.md").write_text("req", encoding="utf-8")
        result = test_vault["registry"].run("approval_watcher")
        assert result["pending_count"] == 2

    def test_counts_approved_items(self, test_vault):
        (test_vault["approved"] / "approved1.md").write_text("ok", encoding="utf-8")
        result = test_vault["registry"].run("approval_watcher")
        assert result["approved_count"] == 1

    def test_counts_rejected_items(self, test_vault):
        (test_vault["rejected"] / "rejected1.md").write_text("no", encoding="utf-8")
        result = test_vault["registry"].run("approval_watcher")
        assert result["rejected_count"] == 1

    def test_returns_file_lists(self, test_vault):
        (test_vault["pending_approval"] / "req.md").write_text("req", encoding="utf-8")
        result = test_vault["registry"].run("approval_watcher")
        assert "req.md" in result["pending"]

    def test_logs_approval_status(self, test_vault):
        test_vault["registry"].run("approval_watcher")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Approval status" in logs


# ── SchedulerSkill Tests ────────────────────────────────────


class TestSchedulerSkill:
    def test_returns_schedule_list(self, test_vault):
        result = test_vault["registry"].run("scheduler")
        assert result["total"] > 0

    def test_has_daily_briefing(self, test_vault):
        result = test_vault["registry"].run("scheduler")
        names = [s["name"] for s in result["schedules"]]
        assert "Daily Briefing" in names

    def test_has_linkedin_check(self, test_vault):
        result = test_vault["registry"].run("scheduler")
        names = [s["name"] for s in result["schedules"]]
        assert "LinkedIn Post Check" in names

    def test_all_schedules_active(self, test_vault):
        result = test_vault["registry"].run("scheduler")
        for s in result["schedules"]:
            assert s["status"] == "active"

    def test_logs_scheduler_report(self, test_vault):
        test_vault["registry"].run("scheduler")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Scheduler report" in logs


# ── CEOBriefingSkill Tests ──────────────────────────────────


class TestCEOBriefingSkill:
    def test_creates_briefing_file(self, test_vault):
        result = test_vault["registry"].run("ceo_briefing")
        assert result["briefing_file"].endswith("_Briefing.md")
        briefings_dir = test_vault["vault"] / "Briefings"
        assert any(f.name.endswith("_Briefing.md") for f in briefings_dir.iterdir())

    def test_briefing_has_executive_summary(self, test_vault):
        result = test_vault["registry"].run("ceo_briefing")
        briefing_file = test_vault["vault"] / "Briefings" / result["briefing_file"]
        content = briefing_file.read_text(encoding="utf-8")
        assert "Executive Summary" in content

    def test_briefing_has_activity_summary(self, test_vault):
        result = test_vault["registry"].run("ceo_briefing")
        briefing_file = test_vault["vault"] / "Briefings" / result["briefing_file"]
        content = briefing_file.read_text(encoding="utf-8")
        assert "Activity Summary" in content

    def test_briefing_counts_done_tasks(self, test_vault):
        (test_vault["done"] / "a.txt").write_text("done", encoding="utf-8")
        (test_vault["done"] / "b.txt").write_text("done", encoding="utf-8")
        result = test_vault["registry"].run("ceo_briefing")
        assert result["done_count"] == 2

    def test_briefing_counts_pending(self, test_vault):
        (test_vault["pending_approval"] / "req.md").write_text("req", encoding="utf-8")
        result = test_vault["registry"].run("ceo_briefing")
        assert result["pending_count"] == 1

    def test_briefing_has_suggestions(self, test_vault):
        result = test_vault["registry"].run("ceo_briefing")
        briefing_file = test_vault["vault"] / "Briefings" / result["briefing_file"]
        content = briefing_file.read_text(encoding="utf-8")
        assert "Proactive Suggestions" in content

    def test_logs_briefing_creation(self, test_vault):
        test_vault["registry"].run("ceo_briefing")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "CEO Briefing generated" in logs


# ── LinkedInAutoPostSkill Tests ─────────────────────────────


class TestLinkedInAutoPostSkill:
    def test_posts_in_dry_run(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("Exciting AI automation update!", encoding="utf-8")
        result = test_vault["registry"].run("linkedin_auto_post", f)
        assert result["mode"] == "dry_run"
        assert result["status"] == "posted_dry_run"

    def test_saves_post_record(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("New post content", encoding="utf-8")
        test_vault["registry"].run("linkedin_auto_post", f)
        posted_dir = test_vault["done"] / "linkedin_posted"
        assert posted_dir.exists()
        posted_files = list(posted_dir.iterdir())
        assert len(posted_files) == 1

    def test_post_record_is_valid_json(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("Post about AI", encoding="utf-8")
        test_vault["registry"].run("linkedin_auto_post", f)
        posted_dir = test_vault["done"] / "linkedin_posted"
        posted_file = list(posted_dir.iterdir())[0]
        data = json.loads(posted_file.read_text(encoding="utf-8"))
        assert "content" in data
        assert "posted_at" in data

    def test_logs_post(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "post.txt"
        f.write_text("LinkedIn post", encoding="utf-8")
        test_vault["registry"].run("linkedin_auto_post", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "LinkedIn" in logs


# ── AuditLogSkill Tests ─────────────────────────────────────


class TestAuditLogSkill:
    def test_creates_json_log_file(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Some task", encoding="utf-8")
        result = test_vault["registry"].run("audit_log", f)
        log_file = test_vault["logs_dir"] / result["log_file"]
        assert log_file.exists()

    def test_log_is_valid_json(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Some task", encoding="utf-8")
        result = test_vault["registry"].run("audit_log", f)
        log_file = test_vault["logs_dir"] / result["log_file"]
        data = json.loads(log_file.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1

    def test_log_has_timestamp(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Some task", encoding="utf-8")
        result = test_vault["registry"].run("audit_log", f)
        log_file = test_vault["logs_dir"] / result["log_file"]
        data = json.loads(log_file.read_text(encoding="utf-8"))
        assert "timestamp" in data[0]

    def test_log_detects_email_action(self, test_vault):
        f = test_vault["needs_action"] / "email_task.txt"
        f.write_text("Send this email", encoding="utf-8")
        result = test_vault["registry"].run("audit_log", f)
        assert result["action_type"] == "email_action"

    def test_log_detects_linkedin_action(self, test_vault):
        f = test_vault["needs_action"] / "linkedin_post.txt"
        f.write_text("Post to LinkedIn", encoding="utf-8")
        result = test_vault["registry"].run("audit_log", f)
        assert result["action_type"] == "linkedin_action"

    def test_multiple_entries_append(self, test_vault):
        f1 = test_vault["needs_action"] / "task1.txt"
        f1.write_text("First", encoding="utf-8")
        f2 = test_vault["needs_action"] / "task2.txt"
        f2.write_text("Second", encoding="utf-8")
        test_vault["registry"].run("audit_log", f1)
        result = test_vault["registry"].run("audit_log", f2)
        assert result["entries_count"] == 2

    def test_logs_audit_entry(self, test_vault):
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Task", encoding="utf-8")
        test_vault["registry"].run("audit_log", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Audit log" in logs


# ── Full Pipeline Tests ─────────────────────────────────────


class TestFullPipeline:
    def test_inbox_to_done_pipeline(self, test_vault):
        """Simulate the full flow via skill registry."""
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("This is urgent", encoding="utf-8")

        test_vault["registry"].run("classify", f)
        test_vault["registry"].run("move_to_done", f)
        test_vault["registry"].run("update_dashboard")

        assert not f.exists()
        done_file = test_vault["done"] / "task.txt"
        assert done_file.exists()
        content = done_file.read_text(encoding="utf-8")
        assert "Urgency: High" in content

    def test_multiple_files_pipeline(self, test_vault):
        """Process three files with different urgencies via skills."""
        files = {
            "urgent.txt": ("This is urgent", "High"),
            "soon.txt": ("Do this soon", "Medium"),
            "normal.txt": ("Just a note", "Low"),
        }

        for name, (text, _) in files.items():
            f = test_vault["needs_action"] / name
            f.write_text(text, encoding="utf-8")
            test_vault["registry"].run("classify", f)
            test_vault["registry"].run("move_to_done", f)

        test_vault["registry"].run("update_dashboard")

        done_files = {f.name for f in test_vault["done"].iterdir()}
        assert done_files == {"urgent.txt", "soon.txt", "normal.txt"}

        dashboard = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "Total Completed** | 3" in dashboard

    def test_logs_capture_full_pipeline(self, test_vault):
        """Verify all log entries appear for one file processed via skills."""
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("urgent task", encoding="utf-8")

        test_vault["registry"].run("classify", f)
        test_vault["registry"].run("move_to_done", f)
        test_vault["registry"].run("update_dashboard")

        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Classified: task.txt" in logs
        assert "Task completed: task.txt" in logs
        assert "Dashboard updated" in logs

    def test_silver_tier_full_pipeline(self, test_vault):
        """Test the complete Silver tier pipeline: classify → plan → approval → done."""
        f = test_vault["needs_action"] / "invoice_task.txt"
        f.write_text("Send invoice payment to Client A for $500", encoding="utf-8")

        # Step 1: Classify
        result = test_vault["registry"].run("classify", f)
        assert result["urgency"] == "Low"  # No "urgent" or "soon" keyword

        # Step 2: Create plan
        plan_result = test_vault["registry"].run("plan_creator", f)
        assert plan_result["needs_approval"] is True
        assert len(list(test_vault["plans"].iterdir())) == 1

        # Step 3: Route to approval
        approval_result = test_vault["registry"].run("human_approval", f)
        assert approval_result["status"] == "awaiting_approval"
        assert approval_result["action_type"] == "payment"
        assert len(list(test_vault["pending_approval"].iterdir())) == 1

        # Step 4: Audit log
        audit_result = test_vault["registry"].run("audit_log", f)
        assert audit_result["action_type"] == "file_action"

        # Step 5: Update dashboard
        test_vault["registry"].run("update_dashboard")
        dashboard = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "Pending Approval | 1" in dashboard

    def test_briefing_after_pipeline(self, test_vault):
        """Test that CEO briefing reflects pipeline activity."""
        # Process some tasks
        for i in range(3):
            f = test_vault["needs_action"] / f"task{i}.txt"
            f.write_text(f"Task {i}", encoding="utf-8")
            test_vault["registry"].run("classify", f)
            test_vault["registry"].run("move_to_done", f)

        # Generate briefing
        result = test_vault["registry"].run("ceo_briefing")
        assert result["done_count"] == 3

        briefing_file = test_vault["vault"] / "Briefings" / result["briefing_file"]
        content = briefing_file.read_text(encoding="utf-8")
        assert "3 tasks completed" in content


# ══════════════════════════════════════════════════════════════
# Gold Tier Tests
# ══════════════════════════════════════════════════════════════


# ── OdooAccountingSkill Tests ─────────────────────────────────


class TestOdooAccountingSkill:
    def test_query_balance_dry_run(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "balance_check.txt"
        f.write_text("Check account balance", encoding="utf-8")
        result = test_vault["registry"].run("odoo_accounting", f)
        assert result["mode"] == "dry_run"
        assert result["action"] == "query_balance"
        assert "accounts" in result

    def test_list_invoices_dry_run(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "list_invoices.txt"
        f.write_text("List all invoices for this month", encoding="utf-8")
        result = test_vault["registry"].run("odoo_accounting", f)
        assert result["action"] == "list_invoices"
        assert "invoices" in result

    def test_create_invoice_dry_run(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "new_invoice.txt"
        f.write_text("Create invoice for Acme Corp", encoding="utf-8")
        result = test_vault["registry"].run("odoo_accounting", f)
        assert result["action"] == "create_invoice"
        assert "invoice_id" in result

    def test_record_payment_dry_run(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "pay_invoice.txt"
        f.write_text("Record payment for invoice INV-001", encoding="utf-8")
        result = test_vault["registry"].run("odoo_accounting", f)
        assert result["action"] == "record_payment"
        assert "payment_id" in result

    def test_profit_loss_dry_run(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "pl_report.txt"
        f.write_text("Generate profit and loss report", encoding="utf-8")
        result = test_vault["registry"].run("odoo_accounting", f)
        assert result["action"] == "profit_loss"
        assert "revenue" in result
        assert "expenses" in result
        assert "net_profit" in result


# ── FacebookPostSkill Tests ──────────────────────────────────


class TestFacebookPostSkill:
    def test_creates_post_record(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "fb_post.txt"
        f.write_text("Exciting AI update for our followers!", encoding="utf-8")
        result = test_vault["registry"].run("facebook_post", f)
        assert result["platform"] == "facebook"
        assert result["status"] == "posted_dry_run"
        posted_dir = test_vault["done"] / "facebook_posted"
        assert posted_dir.exists()
        assert len(list(posted_dir.iterdir())) == 1

    def test_post_record_is_valid_json(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "fb_post.txt"
        f.write_text("Facebook post content", encoding="utf-8")
        test_vault["registry"].run("facebook_post", f)
        posted_dir = test_vault["done"] / "facebook_posted"
        posted_file = list(posted_dir.iterdir())[0]
        data = json.loads(posted_file.read_text(encoding="utf-8"))
        assert data["platform"] == "facebook"
        assert "content" in data
        assert "simulated_engagement" in data

    def test_has_simulated_engagement(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "fb_post.txt"
        f.write_text("Post with engagement", encoding="utf-8")
        result = test_vault["registry"].run("facebook_post", f)
        assert "simulated_engagement" in result
        assert "likes" in result["simulated_engagement"]

    def test_logs_post(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "fb_post.txt"
        f.write_text("Post content", encoding="utf-8")
        test_vault["registry"].run("facebook_post", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Facebook" in logs


# ── InstagramPostSkill Tests ─────────────────────────────────


class TestInstagramPostSkill:
    def test_creates_post_record(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "ig_post.txt"
        f.write_text("Beautiful day for AI! #AI #tech", encoding="utf-8")
        result = test_vault["registry"].run("instagram_post", f)
        assert result["platform"] == "instagram"
        assert result["status"] == "posted_dry_run"
        posted_dir = test_vault["done"] / "instagram_posted"
        assert posted_dir.exists()

    def test_extracts_hashtags(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "ig_post.txt"
        f.write_text("Automation rocks! #AI #Automation #GoldTier", encoding="utf-8")
        result = test_vault["registry"].run("instagram_post", f)
        assert len(result["hashtags"]) == 3
        assert "#AI" in result["hashtags"]

    def test_caption_limit(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "ig_post.txt"
        f.write_text("A" * 3000, encoding="utf-8")  # Over 2200 limit
        result = test_vault["registry"].run("instagram_post", f)
        assert result["char_count"] <= 2200

    def test_has_simulated_engagement(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "ig_post.txt"
        f.write_text("Post content", encoding="utf-8")
        result = test_vault["registry"].run("instagram_post", f)
        assert "simulated_engagement" in result
        assert "saves" in result["simulated_engagement"]


# ── TwitterPostSkill Tests ───────────────────────────────────


class TestTwitterPostSkill:
    def test_creates_tweet_record(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "tweet.txt"
        f.write_text("Just shipped Gold Tier!", encoding="utf-8")
        result = test_vault["registry"].run("twitter_post", f)
        assert result["platform"] == "twitter"
        assert result["status"] == "posted_dry_run"
        posted_dir = test_vault["done"] / "twitter_posted"
        assert posted_dir.exists()

    def test_enforces_280_char_limit(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "tweet.txt"
        f.write_text("A" * 500, encoding="utf-8")
        result = test_vault["registry"].run("twitter_post", f)
        assert result["char_count"] <= 280
        assert result["truncated"] is True

    def test_short_tweet_not_truncated(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "tweet.txt"
        f.write_text("Short tweet", encoding="utf-8")
        result = test_vault["registry"].run("twitter_post", f)
        assert result["truncated"] is False

    def test_has_simulated_engagement(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "tweet.txt"
        f.write_text("Tweet content", encoding="utf-8")
        result = test_vault["registry"].run("twitter_post", f)
        assert "simulated_engagement" in result
        assert "retweets" in result["simulated_engagement"]

    def test_logs_tweet(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "tweet.txt"
        f.write_text("Tweet content", encoding="utf-8")
        test_vault["registry"].run("twitter_post", f)
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Tweet" in logs


# ── SocialMediaSummarySkill Tests ────────────────────────────


class TestSocialMediaSummarySkill:
    def test_empty_summary(self, test_vault):
        result = test_vault["registry"].run("social_media_summary")
        assert result["total_posts"] == 0
        assert result["total_engagement"] == 0

    def test_counts_posts_across_platforms(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        # Create some posts
        f = test_vault["needs_action"] / "fb_post.txt"
        f.write_text("Facebook post", encoding="utf-8")
        test_vault["registry"].run("facebook_post", f)

        f2 = test_vault["needs_action"] / "tweet.txt"
        f2.write_text("Tweet", encoding="utf-8")
        test_vault["registry"].run("twitter_post", f2)

        result = test_vault["registry"].run("social_media_summary")
        assert result["total_posts"] == 2
        assert result["summary"]["facebook"]["post_count"] == 1
        assert result["summary"]["twitter"]["post_count"] == 1

    def test_aggregates_engagement(self, test_vault, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        f = test_vault["needs_action"] / "fb_post.txt"
        f.write_text("Post with engagement", encoding="utf-8")
        test_vault["registry"].run("facebook_post", f)

        result = test_vault["registry"].run("social_media_summary")
        assert result["total_engagement"] > 0

    def test_logs_summary(self, test_vault):
        test_vault["registry"].run("social_media_summary")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Social media summary" in logs


# ── WeeklyBusinessAuditSkill Tests ───────────────────────────


class TestWeeklyBusinessAuditSkill:
    def test_creates_audit_file(self, test_vault):
        result = test_vault["registry"].run("weekly_business_audit")
        assert result["audit_file"].endswith("_Weekly_Audit.md")
        briefings_dir = test_vault["vault"] / "Briefings"
        assert any(f.name.endswith("_Weekly_Audit.md") for f in briefings_dir.iterdir())

    def test_audit_has_financial_summary(self, test_vault):
        result = test_vault["registry"].run("weekly_business_audit")
        audit_file = test_vault["vault"] / "Briefings" / result["audit_file"]
        content = audit_file.read_text(encoding="utf-8")
        assert "Financial Summary" in content
        assert "Revenue" in content
        assert "Expenses" in content

    def test_audit_has_social_media(self, test_vault):
        result = test_vault["registry"].run("weekly_business_audit")
        audit_file = test_vault["vault"] / "Briefings" / result["audit_file"]
        content = audit_file.read_text(encoding="utf-8")
        assert "Social Media Performance" in content

    def test_audit_has_task_performance(self, test_vault):
        (test_vault["done"] / "task1.txt").write_text("done", encoding="utf-8")
        result = test_vault["registry"].run("weekly_business_audit")
        assert result["done_count"] == 1

    def test_audit_returns_financials(self, test_vault):
        result = test_vault["registry"].run("weekly_business_audit")
        assert result["revenue"] == 89500.00
        assert result["expenses"] == 52300.00
        assert result["net_profit"] == 37200.00

    def test_logs_audit_creation(self, test_vault):
        test_vault["registry"].run("weekly_business_audit")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Weekly audit generated" in logs


# ── ErrorRecoverySkill Tests ─────────────────────────────────


class TestErrorRecoverySkill:
    def test_clean_when_no_errors(self, test_vault):
        result = test_vault["registry"].run("error_recovery")
        assert result["status"] == "clean"
        assert result["errors_found"] == 0

    def test_processes_logged_errors(self, test_vault):
        # Create some error log entries
        errors_dir = test_vault["vault"] / "Logs" / "errors"
        errors_dir.mkdir(parents=True, exist_ok=True)
        errors = [
            {"service": "gmail", "error_type": "ConnectionError", "error_message": "timeout"},
            {"service": "odoo", "error_type": "PermissionError", "error_message": "unauthorized"},
        ]
        (errors_dir / "2026-02-23_errors.json").write_text(
            json.dumps(errors), encoding="utf-8"
        )
        result = test_vault["registry"].run("error_recovery")
        assert result["status"] == "processed"
        assert result["errors_found"] == 2
        assert result["recovered"] == 1  # ConnectionError is recoverable

    def test_applies_strategies(self, test_vault):
        errors_dir = test_vault["vault"] / "Logs" / "errors"
        errors_dir.mkdir(parents=True, exist_ok=True)
        errors = [
            {"service": "api", "error_type": "TimeoutError", "error_message": "timed out"},
        ]
        (errors_dir / "2026-02-23_errors.json").write_text(
            json.dumps(errors), encoding="utf-8"
        )
        result = test_vault["registry"].run("error_recovery")
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["strategy"] == "queue_for_retry"

    def test_logs_recovery(self, test_vault):
        test_vault["registry"].run("error_recovery")
        logs = test_vault["logs"].read_text(encoding="utf-8")
        assert "Error recovery" in logs


# ── RetryHandler Tests ───────────────────────────────────────


class TestRetryHandler:
    def test_successful_execution(self, tmp_path):
        handler = RetryHandler(vault_path=tmp_path, max_retries=3, base_delay=0.01)
        result = handler.execute_with_retry(lambda: {"ok": True}, service_name="test")
        assert result == {"ok": True}
        assert handler.stats["total_successes"] == 1

    def test_retries_on_failure(self, tmp_path):
        handler = RetryHandler(vault_path=tmp_path, max_retries=2, base_delay=0.01)
        call_count = [0]

        def flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("failed")
            return {"ok": True}

        result = handler.execute_with_retry(flaky, service_name="test")
        assert result == {"ok": True}
        assert call_count[0] == 3

    def test_exhausts_retries(self, tmp_path):
        handler = RetryHandler(vault_path=tmp_path, max_retries=1, base_delay=0.01)

        def always_fail():
            raise ConnectionError("down")

        result = handler.execute_with_retry(always_fail, service_name="test")
        assert result["status"] == "failed"
        assert handler.stats["total_failures"] == 1

    def test_circuit_breaker_opens(self, tmp_path):
        handler = RetryHandler(vault_path=tmp_path, max_retries=0, base_delay=0.01)
        handler.circuit_breakers["test"].failure_threshold = 2

        def always_fail():
            raise ConnectionError("down")

        handler.execute_with_retry(always_fail, service_name="test")
        handler.execute_with_retry(always_fail, service_name="test")

        # Circuit should be open now
        result = handler.execute_with_retry(always_fail, service_name="test")
        assert result["status"] == "circuit_open"

    def test_logs_errors_to_file(self, tmp_path):
        handler = RetryHandler(vault_path=tmp_path, max_retries=0, base_delay=0.01)

        def fail():
            raise ValueError("test error")

        handler.execute_with_retry(fail, service_name="test_service")
        errors_dir = tmp_path / "Logs" / "errors"
        assert errors_dir.exists()
        error_files = list(errors_dir.iterdir())
        assert len(error_files) == 1

    def test_get_stats(self, tmp_path):
        handler = RetryHandler(vault_path=tmp_path)
        stats = handler.get_stats()
        assert "total_retries" in stats
        assert "total_failures" in stats
        assert "total_successes" in stats
        assert "pending_retries" in stats

    def test_queue_for_retry(self, tmp_path):
        handler = RetryHandler(vault_path=tmp_path)
        handler.queue_for_retry("gmail", {"action": "send", "to": "test@test.com"})
        assert len(handler.get_pending_retries()) == 1


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == "closed"
        assert cb.failure_count == 0

    def test_to_dict(self):
        cb = CircuitBreaker()
        d = cb.to_dict()
        assert "state" in d
        assert "failure_count" in d


# ── RalphWiggumLoop Tests ────────────────────────────────────


class TestRalphWiggumLoop:
    def test_no_active_plans(self, test_vault):
        ralph = RalphWiggumLoop(
            vault_path=test_vault["vault"],
            registry=test_vault["registry"],
        )
        result = ralph.run()
        assert result["status"] == "idle"
        assert result["plans_processed"] == 0

    def test_parses_steps(self, test_vault):
        ralph = RalphWiggumLoop(
            vault_path=test_vault["vault"],
            registry=test_vault["registry"],
        )
        content = "## Steps\n- [ ] Step 1: Do thing\n- [x] Step 2: Done thing\n- [ ] Step 3: Other thing"
        steps = ralph.parse_steps(content)
        assert len(steps) == 3
        assert steps[0]["done"] is False
        assert steps[1]["done"] is True
        assert steps[2]["done"] is False

    def test_matches_skills(self, test_vault):
        ralph = RalphWiggumLoop(
            vault_path=test_vault["vault"],
            registry=test_vault["registry"],
        )
        assert ralph.match_skill("Classify the document urgency") == "classify"
        assert ralph.match_skill("Send email to client") == "gmail_send"
        assert ralph.match_skill("Post to Facebook") == "facebook_post"
        assert ralph.match_skill("Something random") is None

    def test_executes_plan_steps(self, test_vault):
        ralph = RalphWiggumLoop(
            vault_path=test_vault["vault"],
            registry=test_vault["registry"],
        )
        # Create a plan with classifiable step
        plan_content = """---
created: 2026-02-23T10:00:00
source_file: test_task.txt
status: ready
approval_required: False
---

## Steps
- [ ] Step 1: Update dashboard
- [ ] Step 2: Check vault health with vault_watcher
"""
        plan_file = test_vault["plans"] / "PLAN_test_20260223100000.md"
        plan_file.write_text(plan_content, encoding="utf-8")

        result = ralph.run()
        assert result["plans_processed"] == 1
        assert result["total_steps_completed"] >= 1

        # Verify steps were marked done
        updated = plan_file.read_text(encoding="utf-8")
        assert "- [x]" in updated

    def test_respects_max_iterations(self, test_vault):
        ralph = RalphWiggumLoop(
            vault_path=test_vault["vault"],
            registry=test_vault["registry"],
            max_iterations=1,
        )
        plan_content = """---
created: 2026-02-23T10:00:00
source_file: test.txt
status: ready
approval_required: False
---

## Steps
- [ ] Step 1: Update dashboard
- [ ] Step 2: Check vault_watcher health
- [ ] Step 3: Update dashboard again
"""
        plan_file = test_vault["plans"] / "PLAN_test_20260223100000.md"
        plan_file.write_text(plan_content, encoding="utf-8")

        result = ralph.run()
        assert result["iterations_used"] <= 2  # max_iterations + 1 for safety

    def test_skips_approval_required_plans(self, test_vault):
        ralph = RalphWiggumLoop(
            vault_path=test_vault["vault"],
            registry=test_vault["registry"],
        )
        plan_content = """---
created: 2026-02-23T10:00:00
source_file: test.txt
status: pending_approval
approval_required: True
---

## Steps
- [ ] Step 1: Send payment
"""
        plan_file = test_vault["plans"] / "PLAN_test_20260223100000.md"
        plan_file.write_text(plan_content, encoding="utf-8")

        result = ralph.run()
        assert result["plans_processed"] == 0

    def test_get_stats(self, test_vault):
        ralph = RalphWiggumLoop(
            vault_path=test_vault["vault"],
            registry=test_vault["registry"],
        )
        stats = ralph.get_stats()
        assert "active_plans" in stats
        assert "completed_steps" in stats
        assert "max_iterations" in stats

    def test_mark_step_done(self, test_vault):
        ralph = RalphWiggumLoop(
            vault_path=test_vault["vault"],
            registry=test_vault["registry"],
        )
        content = "- [ ] Step 1: Do the thing\n- [ ] Step 2: Another thing"
        updated = ralph.mark_step_done(content, "Step 1: Do the thing")
        assert "- [x] Step 1: Do the thing" in updated
        assert "- [ ] Step 2: Another thing" in updated


# ── Gold Tier Pipeline Tests ─────────────────────────────────


class TestGoldTierPipeline:
    def test_gold_tier_skill_count(self, test_vault):
        assert len(test_vault["registry"].list_skills()) == 23

    def test_cross_domain_workflow(self, test_vault, monkeypatch):
        """Test a workflow spanning accounting + social media."""
        monkeypatch.setenv("DRY_RUN", "true")

        # Step 1: Query accounting
        f = test_vault["needs_action"] / "accounting.txt"
        f.write_text("Check the balance", encoding="utf-8")
        result = test_vault["registry"].run("odoo_accounting", f)
        assert result["mode"] == "dry_run"

        # Step 2: Post results to social media
        f2 = test_vault["needs_action"] / "social_update.txt"
        f2.write_text("Our Q1 revenue hit $89K! Great quarter!", encoding="utf-8")
        fb_result = test_vault["registry"].run("facebook_post", f2)
        assert fb_result["status"] == "posted_dry_run"

        tweet_result = test_vault["registry"].run("twitter_post", f2)
        assert tweet_result["status"] == "posted_dry_run"

        # Step 3: Generate summary
        summary = test_vault["registry"].run("social_media_summary")
        assert summary["total_posts"] >= 2

    def test_full_gold_pipeline(self, test_vault, monkeypatch):
        """Test complete Gold tier pipeline: classify → plan → process → audit."""
        monkeypatch.setenv("DRY_RUN", "true")

        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Review quarterly financials and post update", encoding="utf-8")

        # Classify
        test_vault["registry"].run("classify", f)
        # Plan
        plan_result = test_vault["registry"].run("plan_creator", f)
        # Audit
        test_vault["registry"].run("audit_log", f)
        # Dashboard
        test_vault["registry"].run("update_dashboard")

        dashboard = test_vault["dashboard"].read_text(encoding="utf-8")
        assert "Gold" in dashboard

    def test_briefing_includes_gold_sections(self, test_vault, monkeypatch):
        """Test that CEO briefing has financial and social media sections."""
        monkeypatch.setenv("DRY_RUN", "true")

        result = test_vault["registry"].run("ceo_briefing")
        briefing_file = test_vault["vault"] / "Briefings" / result["briefing_file"]
        content = briefing_file.read_text(encoding="utf-8")
        assert "Financial Summary" in content
        assert "Social Media Performance" in content
        assert "Error Recovery" in content
        assert "Gold Tier" in content

    def test_audit_log_enhanced_fields(self, test_vault):
        """Test that audit log entries have Gold tier fields."""
        f = test_vault["needs_action"] / "task.txt"
        f.write_text("Some task", encoding="utf-8")
        result = test_vault["registry"].run("audit_log", f)
        log_file = test_vault["logs_dir"] / result["log_file"]
        data = json.loads(log_file.read_text(encoding="utf-8"))
        entry = data[0]
        assert "duration_ms" in entry
        assert "mcp_server" in entry
        assert "workflow_id" in entry

    def test_audit_log_mcp_call(self, test_vault):
        """Test MCP call logging."""
        audit_skill = test_vault["registry"].get("audit_log")
        result = audit_skill.log_mcp_call("odoo", "query_balance", duration_ms=150)
        assert result["mcp_server"] == "odoo"
        assert result["tool"] == "query_balance"

    def test_audit_log_ralph_iteration(self, test_vault):
        """Test Ralph loop iteration logging."""
        audit_skill = test_vault["registry"].get("audit_log")
        result = audit_skill.log_ralph_iteration("PLAN_test.md", "Step 1: classify", "completed")
        assert result["plan"] == "PLAN_test.md"
        assert result["status"] == "completed"

    def test_audit_log_cross_domain(self, test_vault):
        """Test cross-domain workflow logging."""
        audit_skill = test_vault["registry"].get("audit_log")
        result = audit_skill.log_cross_domain_workflow(
            "WF-001", ["accounting", "social_media"], "completed"
        )
        assert result["workflow_id"] == "WF-001"

    def test_error_recovery_in_pipeline(self, test_vault):
        """Test error recovery integrates with pipeline."""
        result = test_vault["registry"].run("error_recovery")
        assert result["status"] == "clean"


# ── Odoo MCP Server Tests ───────────────────────────────────


class TestOdooMCPServer:
    def test_query_balance(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.odoo_mcp_server import OdooMCPServer
        server = OdooMCPServer()
        result = server.query_account_balance({"account_type": "all"})
        assert "accounts" in result
        assert result["mode"] == "dry_run"

    def test_list_invoices(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.odoo_mcp_server import OdooMCPServer
        server = OdooMCPServer()
        result = server.list_invoices({"status": "all"})
        assert "invoices" in result
        assert result["total"] >= 0

    def test_create_invoice(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.odoo_mcp_server import OdooMCPServer
        server = OdooMCPServer()
        result = server.create_invoice({
            "client": "Test Corp",
            "amount": 1500.00,
            "description": "Test service",
        })
        assert result["client"] == "Test Corp"
        assert result["mode"] == "dry_run"

    def test_record_payment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.odoo_mcp_server import OdooMCPServer
        server = OdooMCPServer()
        result = server.record_payment({
            "invoice_id": "INV-001",
            "amount": 1500.00,
        })
        assert result["status"] == "recorded"

    def test_profit_loss_report(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.odoo_mcp_server import OdooMCPServer
        server = OdooMCPServer()
        result = server.get_profit_loss_report({"period": "2026-02"})
        assert "revenue" in result
        assert "expenses" in result

    def test_has_5_tools(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.odoo_mcp_server import OdooMCPServer
        server = OdooMCPServer()
        tools = server.get_tools()
        assert len(tools) == 5


# ── Social Media MCP Server Tests ────────────────────────────


class TestSocialMediaMCPServer:
    def test_post_to_facebook(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Done").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.social_media_mcp_server import SocialMediaMCPServer
        server = SocialMediaMCPServer()
        result = server.post_to_facebook({"content": "Hello Facebook!"})
        assert result["platform"] == "facebook"
        assert result["status"] == "posted_dry_run"

    def test_post_to_instagram(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Done").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.social_media_mcp_server import SocialMediaMCPServer
        server = SocialMediaMCPServer()
        result = server.post_to_instagram({
            "caption": "Beautiful #photo",
            "hashtags": ["#photo", "#AI"],
        })
        assert result["platform"] == "instagram"
        assert result["status"] == "posted_dry_run"

    def test_post_to_twitter(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Done").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.social_media_mcp_server import SocialMediaMCPServer
        server = SocialMediaMCPServer()
        result = server.post_to_twitter({"content": "Hello Twitter!"})
        assert result["platform"] == "twitter"
        assert result["status"] == "posted_dry_run"

    def test_twitter_truncation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Done").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.social_media_mcp_server import SocialMediaMCPServer
        server = SocialMediaMCPServer()
        result = server.post_to_twitter({"content": "A" * 500})
        assert result["truncated"] is True
        assert result["char_count"] <= 280

    def test_engagement_summary(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Done").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.social_media_mcp_server import SocialMediaMCPServer
        server = SocialMediaMCPServer()
        # Post something first
        server.post_to_facebook({"content": "Test post"})
        result = server.get_engagement_summary({"platform": "all"})
        assert result["total_posts"] >= 1
        assert "summary" in result

    def test_has_4_tools(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path))
        (tmp_path / "Done").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Logs").mkdir(parents=True, exist_ok=True)

        from mcp_server.social_media_mcp_server import SocialMediaMCPServer
        server = SocialMediaMCPServer()
        tools = server.get_tools()
        assert len(tools) == 4
