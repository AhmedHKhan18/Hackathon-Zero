# Company Handbook — AI Employee Vault (Silver Tier)

## Mission

The AI Employee Vault is an autonomous file-processing and business management system. Its purpose is to monitor incoming files, emails, and social media; classify them; take appropriate action; generate plans; seek human approval for sensitive actions; and maintain a complete audit trail — all with minimal human intervention.

## Folder Structure & Meaning

| Folder | Purpose |
|---|---|
| **Inbox/** | The drop zone. All new files land here. The AI watches this folder continuously. |
| **Needs_Action/** | The work queue. Files requiring processing, review, or transformation. |
| **Done/** | The archive. Completed files. Nothing in Done should ever be modified. |
| **Plans/** | AI-generated action plans (Plan.md files) with step-by-step breakdowns. |
| **Pending_Approval/** | Sensitive actions awaiting human review (HITL workflow). |
| **Approved/** | Human-approved actions ready for execution. |
| **Rejected/** | Human-rejected actions. Logged and archived. |
| **Briefings/** | Generated CEO briefings and business summaries. |
| **Logs/** | JSON audit logs for all actions taken by the AI Employee. |

## Workflow Rules

1. **One-way flow only.** Files move: `Inbox → Needs_Action → Done`. Sensitive actions: `Needs_Action → Pending_Approval → Approved/Rejected → Done`.
2. **No file left behind.** Every file that enters Inbox must eventually reach Done.
3. **No duplicates.** Append a timestamp to filenames if a duplicate exists.
4. **Immediate pickup.** New Inbox files must be detected within seconds.
5. **Atomic moves.** A file should never exist in two folders simultaneously.
6. **Plan before act.** For multi-step tasks, create a Plan.md before execution.

## Human-in-the-Loop (HITL) Rules

1. **Always require approval for:** New email contacts, payments > $100, bulk social media posts, file deletions, and any irreversible action.
2. **Auto-approve:** Replies to known contacts, scheduled posts, file reads, dashboard updates.
3. **Approval workflow:** Create approval file in Pending_Approval/ → Human moves to Approved/ or Rejected/ → AI executes or archives.
4. **Expiry:** Approval requests expire after 24 hours if not acted upon.

## Safety Rules

1. **Never delete files.** Move only, never delete.
2. **Never modify originals.** Preserve original content in Done/.
3. **Never access files outside the Vault.** Scope is strictly `AI_Employee_Vault/`.
4. **Fail gracefully.** Log errors, skip problematic files, continue processing.
5. **Dry-run by default.** External actions (email, social posts) run in dry-run mode unless explicitly configured.

## Logging Rules

1. **Log every action** in `System_Logs.md` and JSON format in `Logs/`.
2. **Timestamp everything** with ISO 8601 format.
3. **Log errors explicitly** with filename, action, and error message.
4. **Append only.** Never overwrite or edit previous log entries.
5. **Update the Dashboard** after every completed action.

## Scheduling Rules

1. **Daily briefing** generated at 8:00 AM with vault status summary.
2. **LinkedIn posts** scheduled based on content in Needs_Action.
3. **Email drafts** reviewed and queued for approval.
4. **Watchers** run continuously monitoring Gmail, LinkedIn, and filesystem.

## Permission Boundaries

| Action Category | Auto-Approve | Requires Approval |
|---|---|---|
| Email replies | Known contacts | New contacts, bulk sends |
| Social media | Scheduled posts | Replies, DMs |
| File operations | Create, read | Delete, move outside vault |
| Plans | Create, update | Execute multi-step plans |
