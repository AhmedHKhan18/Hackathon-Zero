# Dashboard — AI Employee Vault (Platinum Tier)

## System Status

| Field | Value |
|---|---|
| **Status** | ONLINE |
| **Tier** | Platinum |
| **Last Updated** | 2026-04-15 |
| **Local Agent** | ONLINE |
| **Cloud Agent** | PENDING SETUP |
| **Total Completed** | 32 |

## File Counts

| Folder | Count |
|---|---|
| Inbox | 0 |
| Needs Action (cloud) | 0 |
| Needs Action (local) | 0 |
| Done | 32 |
| Plans | 59 |
| Pending Approval | 0 |
| Drafts | 0 |
| Updates | 0 |
| Signals | 0 |

## Approval Queue

| Status | Count |
|---|---|
| Pending | 0 |
| Approved | 0 |
| Rejected | 0 |

## Platinum Tier Work-Zone Split

| Zone | Owns |
|---|---|
| **Cloud Agent (24/7)** | Email triage, draft replies, social post drafts, Odoo draft invoices, health heartbeat |
| **Local Agent (on-demand)** | Approvals, WhatsApp, banking/payments, final send/post, Dashboard.md |

## Vault Sync Strategy

- **Method:** Git (private repository)
- **Cloud pushes:** /Pending_Approval/, /Drafts/, /Updates/, /Signals/
- **Local pushes:** /Approved/, /Done/, /Plans/, Dashboard.md
- **Secrets:** Never synced — stay in local .env on each machine
- **Claim rule:** First agent to move file from /Needs_Action/ to /In_Progress/<agent>/ owns it

## Active Agents

| Agent | Location | Status | Last Heartbeat |
|---|---|---|---|
| local-agent | Local Machine | ONLINE | — |
| cloud-agent | Oracle Cloud VM | PENDING SETUP | — |

---
*Written by Local Agent only (single-writer rule). Cloud writes to /Updates/ — merged here.*
