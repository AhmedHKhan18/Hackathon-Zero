# Company Handbook — AI Employee Vault

## Mission

The AI Employee Vault is an autonomous file-processing system. Its purpose is to monitor incoming files, classify them, take the appropriate action, and maintain a complete audit trail — all without human intervention. The system operates as a reliable digital employee that never sleeps, never forgets, and never acts outside its defined rules.

## Folder Structure & Meaning

| Folder | Purpose |
|---|---|
| **Inbox/** | The drop zone. All new files land here. The AI watches this folder continuously and picks up any file that appears. |
| **Needs_Action/** | The work queue. Files that require processing, review, or transformation are moved here while the AI works on them. |
| **Done/** | The archive. Completed files are moved here once all actions are finished. Nothing in Done should ever be modified. |

## Workflow Rules

1. **One-way flow only.** Files move in one direction: `Inbox → Needs_Action → Done`. Files must never move backwards.
2. **No file left behind.** Every file that enters Inbox must eventually reach Done. If processing fails, the file stays in Needs_Action and an error is logged.
3. **No duplicates.** If a file with the same name already exists in the destination folder, append a timestamp to the filename before moving.
4. **Immediate pickup.** The AI must detect and begin processing new Inbox files within seconds of their arrival.
5. **Atomic moves.** File moves must be atomic — a file should never exist in two folders at the same time.

## Safety Rules

1. **Never delete files.** The AI may move files but must never delete any file under any circumstance.
2. **Never modify originals.** The original file content must be preserved as-is when moved to Done.
3. **Never access files outside the Vault.** The AI's filesystem scope is limited strictly to the `AI_Employee_Vault/` directory and its subfolders.
4. **Fail gracefully.** If an error occurs, log it, skip the problematic file, and continue processing the next one. Never crash silently.
5. **No external network calls.** The AI operates entirely offline on the local filesystem.

## Logging Rules

1. **Log every action.** Every file pickup, move, and completion must be recorded in `System_Logs.md`.
2. **Timestamp everything.** All log entries must include an ISO 8601 timestamp (e.g., `2026-02-17T14:30:00`).
3. **Log errors explicitly.** Errors must include the filename, the action that failed, and the error message.
4. **Append only.** Logs are append-only. Never overwrite or edit previous log entries.
5. **Update the Dashboard.** After every completed action, update `Dashboard.md` with current file counts and system status.
