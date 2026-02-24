# Lessons Learned — AI Employee Hackathon

## Development Journey

### Bronze Tier
Built the foundation: file watching with watchdog, skill registry pattern, classify/plan/move pipeline, Obsidian vault structure, and HITL approval workflow.

**Key decision:** Using an Obsidian vault as the data layer. Files as the unit of work made everything inspectable, debuggable, and human-friendly. No database needed.

**Key decision:** Skill registry pattern. Each skill is self-contained with `execute()` returning a dict. This made testing trivial and composition natural.

### Silver Tier
Added WhatsApp/LinkedIn watchers, plan creator, approval workflow, CEO briefings, audit logging, and the email MCP server.

**Key decision:** Abstract `BaseWatcher` class. All watchers share the same poll-check-create pattern, making new integrations predictable.

**Key decision:** JSON audit logs alongside markdown system logs. JSON for machines, markdown for humans.

### Gold Tier
Added Odoo accounting, Facebook/Instagram/Twitter posting, Ralph Wiggum autonomous loop, error recovery with circuit breakers, two new MCP servers, weekly audits, and comprehensive testing.

**Key decision:** Ralph Wiggum loop uses keyword matching to map plan steps to skills. Simple but effective for autonomous execution without an LLM in the loop.

**Key decision:** Circuit breaker pattern prevents cascading failures when external services go down.

---

## What Worked Well

1. **Dry-run first development** — Every external action has a dry-run mode that returns realistic simulated data. This made development fast and safe. Tests run without any API credentials.

2. **File-based architecture** — The vault folder structure (Inbox → Needs_Action → Done) is simple, visible, and debuggable. You can inspect the system state by looking at folders.

3. **Skill registry pattern** — Adding new skills is just: write a class, register it. The registry handles routing. This scaled from 9 to 23 skills without any architectural changes.

4. **Comprehensive fixture data** — `odoo_samples.json` provides realistic invoices, balances, and P&L data. Simulated engagement metrics make social media dry-runs feel real.

5. **Test-driven confidence** — 190 tests covering every skill, both MCP servers, the retry handler, and the Ralph loop. Refactoring was safe because tests caught regressions immediately.

---

## Challenges

1. **Encoding handling on Windows** — Files created by different programs use different encodings (UTF-8, UTF-16, BOM). The `_read_file()` fallback chain solved this, but it was a surprising source of early bugs.

2. **Plan step → skill matching** — The keyword-based matching in Ralph loop is fragile. Steps like "Process the invoice payment" could match multiple skills. Priority ordering in the keyword dict mitigates this.

3. **Approval workflow complexity** — The HITL approval flow (Pending_Approval → Approved/Rejected → execute → Done) has many edge cases: expired approvals, modified files, concurrent access. The claim-by-move pattern helps but isn't bulletproof.

4. **Cross-domain coordination** — A task like "send invoice and post about it on social media" spans multiple skills. The orchestrator detects these but doesn't yet have sophisticated sequencing.

---

## Recommendations for Future Work

1. **Add an LLM in the loop** — Replace keyword matching in Ralph loop with an actual Claude API call for step-to-skill mapping. This would handle ambiguous steps much better.

2. **Real Odoo integration** — The XML-RPC client for Odoo is straightforward. The dry-run fixtures model the exact data shape, so switching to live mode is mostly plumbing.

3. **Webhook-based watchers** — Polling is simple but wasteful. Gmail, LinkedIn, and social platforms all support webhooks that would reduce latency and API calls.

4. **Persistent error queue** — Currently the retry queue is in-memory. Persisting it to a JSON file in the vault would survive restarts.

5. **Dashboard UI** — The markdown Dashboard.md is functional but static. A simple web dashboard (Flask/FastAPI) could show real-time status, approval buttons, and charts.

6. **Multi-tenant support** — The vault-per-employee model could scale to multiple AI employees, each with their own vault and skill configuration.

---

## Architecture Principles

These principles guided all three tiers:

1. **Files are the API** — Drop a file, get a result. No REST endpoints, no message queues.
2. **Dry-run by default** — Never send a real email or post until explicitly switched to live mode.
3. **Audit everything** — Every action logged in both human-readable markdown and machine-readable JSON.
4. **Human in the loop** — Sensitive actions require explicit approval via folder moves.
5. **Graceful degradation** — If a service is down, queue locally and retry later.
6. **Test everything** — If it's not tested, it doesn't work. 190 tests prove the system.

---

*Hackathon 0 — Bronze → Silver → Gold*
