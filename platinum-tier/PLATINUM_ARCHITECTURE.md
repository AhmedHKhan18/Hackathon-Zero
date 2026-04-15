# Platinum Tier Architecture — AI Employee (Always-On Cloud + Local Executive)

## Overview

Platinum Tier transforms the Gold Tier local AI Employee into a **distributed, 24/7 system**
with a Cloud Agent running continuously on a VM and a Local Agent handling sensitive
approvals and actions on-demand.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PLATINUM TIER ARCHITECTURE                      │
├─────────────────────────────┬───────────────────────────────────────┤
│     CLOUD VM (24/7)         │          LOCAL MACHINE               │
│                             │                                       │
│  ┌─────────────────────┐    │    ┌──────────────────────────┐      │
│  │   cloud_agent.py    │    │    │      local_agent.py      │      │
│  │                     │    │    │                          │      │
│  │  • Email triage     │    │    │  • Execute approvals     │      │
│  │  • Draft replies    │    │    │  • WhatsApp replies      │      │
│  │  • Social drafts    │    │    │  • Banking / payments    │      │
│  │  • Odoo drafts      │    │    │  • Final send/post       │      │
│  │  • Health beats     │    │    │  • Dashboard.md (owner)  │      │
│  └────────┬────────────┘    │    └────────────┬─────────────┘      │
│           │                 │                 │                     │
│  ┌────────▼────────────┐    │    ┌────────────▼─────────────┐      │
│  │  health_monitor.py  │    │    │      gmail_watcher.py    │      │
│  │  • HTTP /health     │    │    │      whatsapp_watcher.py │      │
│  │  • Watchdog         │    │    │      linkedin_watcher.py │      │
│  │  • Heartbeat        │    │    └──────────────────────────┘      │
│  └─────────────────────┘    │                                       │
├─────────────────────────────┴───────────────────────────────────────┤
│                                                                     │
│                    SHARED VAULT (Git Sync)                          │
│                                                                     │
│   /Needs_Action/cloud/   ←── Cloud picks up new email tasks        │
│   /Needs_Action/local/   ←── Local picks up WhatsApp tasks         │
│   /In_Progress/cloud-agent/  ←── Claimed tasks (cloud)             │
│   /In_Progress/local-agent/  ←── Claimed tasks (local)             │
│   /Pending_Approval/     ←── Cloud writes; Local reads & approves  │
│   /Approved/             ←── User approves; Local executes          │
│   /Rejected/             ←── User rejects; archived                │
│   /Drafts/               ←── Email/social drafts (cloud writes)    │
│   /Updates/              ←── Cloud signals; Local merges           │
│   /Signals/health.md     ←── Cloud heartbeat; Local checks          │
│   /Done/                 ←── Completed tasks (both agents write)   │
│   Dashboard.md           ←── LOCAL ONLY (single-writer rule)       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Work-Zone Specialization

### Cloud Owns (runs 24/7 on VM)
| Responsibility | Implementation |
|---|---|
| Email triage | `gmail_watcher.py` writes to `/Needs_Action/cloud/` |
| Draft email replies | `CloudEmailDraftSkill` → `/Drafts/` + `/Pending_Approval/` |
| Social post drafts | Cloud drafts, writes to `/Pending_Approval/cloud/` |
| Odoo draft invoices | `OdooCloudDraftSkill` → draft only, never posts |
| Health heartbeat | `CloudHealthMonitorSkill` → `/Signals/health.md` |
| Vault sync pull/push | `VaultSync` after each action cycle |

### Local Owns (runs on user's machine)
| Responsibility | Implementation |
|---|---|
| WhatsApp session | `whatsapp_watcher.py` (Playwright, local browser) |
| Banking / payments | Never on cloud; Local MCP only |
| Approval execution | `LocalApprovalExecutorSkill` watches `/Approved/` |
| Dashboard.md | **Single-writer rule** — only `local_agent.py` writes it |
| Update merging | `DashboardMergeSkill` merges `/Updates/` into Dashboard |
| Health checking | Reads `/Signals/health.md`, alerts if stale (>10 min) |

---

## 2. Claim-By-Move Rule (Preventing Double Work)

When both Cloud and Local agents are running, they must not process the same task.

```
/Needs_Action/<task>.md
        │
        │  First agent to move it wins
        ▼
/In_Progress/<agent-id>/<task>.md  ← CLAIMED
        │
        │  Processing complete
        ▼
/Done/<task>.md  ← ARCHIVED
```

Rules:
1. Agent checks if file exists in any other `/In_Progress/<other-agent>/`
2. If not claimed: atomically moves file to `/In_Progress/<own-agent-id>/`
3. If race lost (another agent moved it first): skip silently
4. Stale claims (>30 min): `VaultCleanupSkill` returns them to `/Needs_Action/`

Implemented in: `platinum_skills.py → ClaimByMoveSkill`

---

## 3. Vault Sync via Git

```
Cloud VM                                    Local Machine
─────────────────────────────────────────────────────────
Write draft → git add → git commit → git push
                                         ↓ (git pull)
                              Local reads new drafts
                              User approves
                              Local executes
                              git add → git commit → git push
                                         ↑ (git pull)
Cloud sees completed tasks
```

### Security Rules
- `.gitignore` enforced by `VaultSync.ensure_gitignore()`
- **Never synced:** `.env`, `token.json`, `credentials.json`, `*.key`, `*.pem`
- **Only synced:** `AI_Employee_Vault/` markdown and state files
- Secrets stay in local `.env` on each machine independently

### Setup
```bash
# On local machine: initialize vault repo
cd platinum-tier
git init
git remote add origin git@github.com:<you>/ai-employee-vault.git
git push -u origin main

# On cloud VM: clone and set up SSH deploy key
ssh-keygen -t ed25519 -C "cloud-agent"
# Add ~/.ssh/id_ed25519.pub as a GitHub deploy key (read-write)
git clone git@github.com:<you>/ai-employee-vault.git
```

---

## 4. Platinum Demo (Minimum Passing Gate)

The hackathon requires this flow to work end-to-end:

```
Email arrives (Local offline)
      │
      ▼  [Cloud Agent — continuous]
Gmail Watcher detects unread email
      │
      ▼
Creates /Needs_Action/cloud/EMAIL_<id>.md
      │
      ▼
cloud_agent.py claims it → /In_Progress/cloud-agent/EMAIL_<id>.md
      │
      ▼
CloudEmailDraftSkill:
  - Writes /Drafts/EMAIL_<id>_<ts>.md (draft reply)
  - Writes /Pending_Approval/EMAIL_REPLY_<id>_<ts>.md (approval request)
  - Writes /Updates/cloud_draft_<id>.md (signal to Local)
      │
      ▼
VaultSync.push() → git push → remote repo updated
      │
      ▼  [Local Agent — user returns]
VaultSync.pull() → local vault updated
      │
      ▼
DashboardMergeSkill processes /Updates/ → Dashboard.md updated
      │
      ▼
User sees approval request in /Pending_Approval/
User moves file to /Approved/
      │
      ▼
LocalApprovalExecutorSkill executes send_email via Gmail API
      │
      ▼
Logs action in System_Logs.md
Moves task to /Done/
      │
      ▼
VaultSync.push() → remote updated
Cloud agent sees completed task on next pull
```

### Run the Demo
```bash
# Terminal 1: Start cloud agent (simulates 24/7 cloud)
python cloud_agent.py --vault-path AI_Employee_Vault --interval 10

# Terminal 2: Create demo email task
python local_agent.py --vault-path AI_Employee_Vault --demo

# Wait for cloud_agent to process the email...
# Then approve by moving the approval file:
mv "AI_Employee_Vault/Pending_Approval/EMAIL_REPLY_*.md" AI_Employee_Vault/Approved/

# Terminal 3: Run local agent to execute the approval
python local_agent.py --vault-path AI_Employee_Vault
```

---

## 5. Odoo Cloud Deployment (24/7 with HTTPS + Backups)

```yaml
# docker-compose.yml (included — for local dev)
# For cloud: deploy on same VM as cloud_agent
services:
  odoo:
    image: odoo:19.0
    ports: ["8069:8069"]
    restart: always
  db:
    image: postgres:16
    restart: always
```

### Cloud VM Setup with HTTPS
```bash
# Install certbot for Let's Encrypt
sudo snap install certbot --classic
sudo certbot --nginx -d odoo.yourdomain.com

# Add to nginx for Odoo HTTPS
location / {
    proxy_pass http://127.0.0.1:8069;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Host $host;
}
```

### Backups
```bash
# Add to cron: daily Odoo database backup
0 2 * * * docker exec odoo_db pg_dump -U odoo odoo > /backups/odoo_$(date +%Y%m%d).sql
# Keep 7 days
find /backups -name "odoo_*.sql" -mtime +7 -delete
```

### Health Monitoring
- Odoo health: `curl http://localhost:8069/web/health`
- Add to `health_monitor.py` if needed

---

## 6. Phase 2: A2A Upgrade (Optional)

Replace some file handoffs with direct Agent-to-Agent (A2A) messages while keeping
vault as the audit record:

```python
# Instead of writing a file and waiting for git sync:
# Cloud agent directly notifies Local agent via A2A protocol
import anthropic

client = anthropic.Anthropic()
# Send task directly to local agent via A2A
# Vault still gets the audit record written
```

Phase 2 reduces latency from git-sync cycles (60s+) to near-real-time.
The vault file remains as the permanent audit trail regardless.

---

## 7. Files Added for Platinum Tier

| File | Purpose |
|---|---|
| `cloud_agent.py` | Cloud-side 24/7 orchestrator |
| `local_agent.py` | Local-side approval executor |
| `platinum_skills.py` | 8 new platinum agent skills |
| `vault_sync.py` | Git-based vault synchronization |
| `health_monitor.py` | Cloud agent health + HTTP endpoint |
| `cloud_deploy/setup_cloud.sh` | Oracle Cloud VM setup script |
| `cloud_deploy/cloud-agent.service` | systemd service for cloud agent |
| `cloud_deploy/health-monitor.service` | systemd service for health monitor |
| `cloud_deploy/nginx-ai-employee.conf` | nginx config for health check |
| `.env.cloud.example` | Cloud environment variables template |
| `PLATINUM_ARCHITECTURE.md` | This document |

### New Vault Directories
| Directory | Owner | Purpose |
|---|---|---|
| `/Needs_Action/cloud/` | Cloud | Email + Odoo tasks for cloud |
| `/Needs_Action/local/` | Local | WhatsApp + payment tasks |
| `/In_Progress/cloud-agent/` | Cloud | Claimed tasks (cloud) |
| `/In_Progress/local-agent/` | Local | Claimed tasks (local) |
| `/Drafts/` | Cloud | Email draft replies |
| `/Updates/` | Cloud | Signals to Local |
| `/Signals/` | Cloud | Health heartbeat files |

---

## 8. Lessons Learned (Platinum)

1. **Git sync latency is acceptable for this use case.** A 60-second sync window means
   email replies are drafted within 2 minutes of arrival — fast enough for business use.

2. **The single-writer rule for Dashboard.md is critical.** Without it, both agents
   overwrite each other's updates and the dashboard becomes unreliable.

3. **Claim-by-move beats distributed locks.** File system moves are atomic (on the same
   volume), making them a simple and reliable coordination primitive.

4. **Secrets must never cross the network.** The cloud agent only needs Gmail API token
   and Odoo credentials. WhatsApp and banking tokens never leave the local machine.

5. **Health monitoring catches silent failures.** A crashed cloud agent writing nothing
   is detected by the stale heartbeat check within 10 minutes.

6. **Oracle Cloud Always Free tier is sufficient.** 1 OCPU + 1GB RAM comfortably runs
   cloud_agent.py + health_monitor.py + Odoo (with the lightweight ARM builds).
