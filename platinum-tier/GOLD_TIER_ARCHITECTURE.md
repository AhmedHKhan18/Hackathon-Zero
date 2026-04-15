# Gold Tier Architecture — AI Employee System

## Overview

The Gold Tier AI Employee is a fully autonomous file-processing and business management system built on Python. It monitors an Obsidian vault for incoming tasks, classifies them, creates plans, executes actions across multiple domains (accounting, email, social media), and maintains comprehensive audit trails.

**23 skills | 3 watchers | 3 MCP servers | Ralph Wiggum autonomous loop | Error recovery**

---

## System Architecture

```
                    ┌──────────────────────┐
                    │      main.py         │
                    │  (Watchdog Observer)  │
                    └──────┬───────────────┘
                           │
              ┌────────────┼────────────────┐
              │            │                │
        ┌─────▼─────┐ ┌───▼────┐   ┌───────▼───────┐
        │  Inbox/    │ │Approved│   │   scheduler   │
        │  Handler   │ │Handler │   │    .py        │
        └─────┬──────┘ └───┬────┘   └───────┬───────┘
              │            │                │
              └────────────┼────────────────┘
                           │
                    ┌──────▼──────────────┐
                    │   orchestrator.py    │
                    │  (Gold Tier Master)  │
                    ├─────────────────────┤
                    │ • process_needs_action│
                    │ • process_approved    │
                    │ • execute_ralph_loop  │
                    │ • cross_domain_tasks  │
                    │ • error_recovery      │
                    └──────┬──────────────┘
                           │
              ┌────────────┼────────────────┐
              │            │                │
       ┌──────▼──────┐ ┌──▼───────┐  ┌─────▼──────┐
       │ SkillRegistry│ │ Ralph    │  │  Retry     │
       │ (23 skills) │ │ Loop     │  │  Handler   │
       └──────┬──────┘ └──┬───────┘  └─────┬──────┘
              │            │                │
              └────────────┼────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼─────┐    ┌──────▼─────┐    ┌──────▼──────┐
    │  Email   │    │   Odoo     │    │Social Media │
    │  MCP     │    │   MCP      │    │   MCP       │
    │  Server  │    │   Server   │    │   Server    │
    └──────────┘    └────────────┘    └─────────────┘
```

---

## Component Details

### Skill Registry (`agent_skills.py`)

23 modular skills organized by tier:

| Tier | Skills | Count |
|------|--------|-------|
| Bronze | classify, move_to_done, update_dashboard, task_planner, vault_file_manager, vault_watcher, human_approval, gmail_send, linkedin_post | 9 |
| Silver | whatsapp_reply, plan_creator, approval_watcher, scheduler, ceo_briefing, linkedin_auto_post, audit_log | 7 |
| Gold | odoo_accounting, facebook_post, instagram_post, twitter_post, social_media_summary, weekly_business_audit, error_recovery | 7 |

Each skill inherits from `AgentSkill` base class with:
- `name` / `description` — identity
- `execute(file_path)` — core action
- `log_entry(message)` — audit trail
- `_read_file(path)` — encoding-safe file reader

### Watchers

| Watcher | Source | Frequency |
|---------|--------|-----------|
| `gmail_watcher.py` | Gmail API / email_drops/ | Every 2 min |
| `linkedin_watcher.py` | LinkedIn API / linkedin_posts/ | Every 30 min |
| `whatsapp_watcher.py` | WhatsApp Web / whatsapp_drops/ | Continuous |

### MCP Servers (`mcp_server/`)

All MCP servers use JSON-RPC over stdio, compatible with Claude Code.

| Server | Tools | File |
|--------|-------|------|
| Email | send_email, create_draft, list_drafts, search_emails | `email_mcp_server.py` |
| Odoo | query_account_balance, list_invoices, create_invoice, record_payment, get_profit_loss_report | `odoo_mcp_server.py` |
| Social Media | post_to_facebook, post_to_instagram, post_to_twitter, get_engagement_summary | `social_media_mcp_server.py` |

### Ralph Wiggum Loop (`ralph_loop.py`)

Autonomous plan executor that:
1. Finds Plan.md files with unchecked steps (`- [ ]`)
2. Matches each step to a registered skill via keyword mapping
3. Executes the skill and marks the step done (`- [x]`)
4. Stops on: all done, max iterations, or approval needed
5. Uses claim-by-move pattern (`In_Progress/`) to prevent duplicates

### Error Recovery (`retry_handler.py`)

- **Exponential backoff**: configurable base delay, max delay, max retries
- **Circuit breaker**: opens after N failures, auto-recovers after timeout
- **Error queue**: failed tasks queued for later retry
- **Error logging**: JSON logs to `Logs/errors/`

---

## Data Flow

### Standard Pipeline
```
File dropped in Inbox/
  → InboxHandler moves to Needs_Action/
    → ClassifySkill assigns urgency
      → PlanCreatorSkill creates Plan.md
        → Route: approval needed?
          YES → HumanApprovalSkill → Pending_Approval/
          NO  → MoveToeDoneSkill → Done/
        → AuditLogSkill logs action
        → UpdateDashboardSkill refreshes Dashboard.md
```

### Ralph Wiggum Autonomous Loop
```
Orchestrator cycle
  → ralph_loop.run()
    → Find active plans in Plans/
      → Claim plan (copy to In_Progress/)
        → For each unchecked step:
          → Match step text to skill keyword
          → Execute skill
          → Mark step [x] done
        → Release plan back to Plans/
```

### Approval Workflow
```
Sensitive task detected
  → HumanApprovalSkill creates APPROVAL_*.md
    → File placed in Pending_Approval/
      → Human moves to Approved/ or Rejected/
        → ApprovalHandler executes action
          → File archived in Done/
```

---

## Vault Folder Structure

```
AI_Employee_Vault/
├── Inbox/                    # Drop zone (monitored by watchdog)
│   ├── email_drops/          # Simulated email messages
│   ├── linkedin_posts/       # LinkedIn post queue
│   ├── linkedin_notifications/
│   └── whatsapp_drops/       # Simulated WhatsApp messages
├── Needs_Action/             # Work queue
├── In_Progress/              # Claimed by Ralph loop
├── Done/                     # Completed archive
│   ├── facebook_posted/      # Facebook post records
│   ├── instagram_posted/     # Instagram post records
│   ├── twitter_posted/       # Twitter post records
│   └── linkedin_posted/      # LinkedIn post records
├── Plans/                    # Plan.md files with checklists
├── Pending_Approval/         # HITL review queue
├── Approved/                 # Human-approved actions
├── Rejected/                 # Human-rejected actions
├── Briefings/                # CEO briefings + weekly audits
├── Drafts/                   # Email/social drafts (JSON)
├── Logs/                     # JSON audit logs
│   └── errors/               # Error recovery logs
├── Business_Goals.md
├── Company_Handbook.md
├── Dashboard.md              # Auto-updated status
└── System_Logs.md            # Human-readable log
```

---

## Configuration

### Dry-Run vs Live Mode

All external actions default to `DRY_RUN=true`:

| Component | Dry-Run Behavior | Live Behavior |
|-----------|-----------------|---------------|
| Email | Creates draft JSON in vault | Sends via Gmail API |
| LinkedIn | Saves post record to Done/ | Posts via LinkedIn API |
| Facebook | Saves record + simulated engagement | Posts via Graph API |
| Instagram | Saves record + simulated engagement | Posts via Graph API |
| Twitter | Saves record + simulated engagement | Posts via API v2 |
| Odoo | Returns fixture data from odoo_samples.json | Queries real Odoo instance |

### Environment Variables

See `.env.example` for all configuration options including:
- API credentials for each platform
- Retry handler settings (max attempts, delays)
- Ralph loop settings (max iterations, enabled flag)

---

## Error Recovery Strategies

| Error Type | Strategy |
|-----------|----------|
| ConnectionError | Queue for retry with exponential backoff |
| TimeoutError | Queue for retry with exponential backoff |
| PermissionError | Flag for human review |
| AuthenticationError | Flag for human review |
| Other | Log for review |

Circuit breaker opens after 3 consecutive failures per service, auto-recovers after 60 seconds.

---

## Running the System

```bash
# Start the file watcher (23 skills, watches Inbox/ and Approved/)
python main.py

# Start the full orchestrator (includes Ralph loop + error recovery)
python orchestrator.py

# Start the scheduler (daily briefings, weekly audits, health checks)
python scheduler.py

# Test MCP servers
python mcp_server/email_mcp_server.py --test
python mcp_server/odoo_mcp_server.py --test
python mcp_server/social_media_mcp_server.py --test

# Run all tests (190 tests)
pytest test_main.py -v
```

---

## Testing

190 tests across 27 test classes covering:
- All 23 skills individually
- Skill registry (23 skills registered)
- Full pipeline (Bronze → Silver → Gold)
- Retry handler + circuit breaker
- Ralph Wiggum loop (plan parsing, execution, iteration limits)
- Cross-domain workflows
- Both MCP servers (all 9 tools in dry-run)
- Enhanced audit logging (MCP calls, Ralph iterations, cross-domain)

---

*AI Employee v0.3 — Gold Tier*
