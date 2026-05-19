# PlotLot Autonomy + Continuity Plan

> **For Hermes:** use this to keep momentum between sessions, survive context compaction, and prevent long-running work from silently stalling.

**Goal:** Make PlotLot work continue even when the live chat gets interrupted, the model context gets compacted, or a background run stalls.

**Architecture:** Split the system into 4 layers: (1) durable state files inside the repo, (2) a background runner with logs and heartbeat output, (3) an automatic watchdog/check-in loop, and (4) a strict handoff format so any new session can resume instantly.

**Tech Stack:** Markdown handoff docs, JSON status file, background process management, cron heartbeat, repo-local logs.

---

## Root Cause

We lost momentum for two reasons:

1. **Autonomous execution had no durable supervisor**
   - processes could stay alive while useful work stopped
   - no automatic detection of “alive but stalled”
   - no required next-action queue

2. **Session continuity depended too much on chat memory**
   - important state lived in conversation context instead of files
   - when context compacted, the thread lost the current work frontier
   - there was no canonical resume artifact in the repo

---

## The Fix: 4-Part Operating System

## 1) Canonical repo-local handoff file

Create and maintain a single source of truth:

- `docs/status/CURRENT_STATE.md`

This file should always answer:
- what is working right now
- what is broken right now
- exact commands to restart stack
- last verified address / test case
- last completed fix
- next 3 highest-priority tasks
- known risks / blockers
- where logs live

### Required template

```md
# Current State

## Stack
- frontend:
- backend:
- database:
- background jobs:

## Last Verified
- timestamp:
- command(s):
- result:

## Working
- ...

## Broken / Gaps
- ...

## Next Actions
1. ...
2. ...
3. ...

## Resume Commands
```bash
# exact commands here
```

## Evidence
- log path:
- test path:
- screenshot path:
```

Rule: every meaningful work session updates this file before stopping.

---

## 2) Machine-readable status file

Create:

- `docs/status/runtime-status.json`

This should be updated by scripts and contain:
- `updated_at`
- `frontend_url`
- `backend_url`
- `backend_pid` or Hermes process session id
- `health_status`
- `last_analysis_address`
- `last_analysis_result`
- `open_issues`
- `next_action`

Why: a future agent/session can parse JSON faster and more reliably than digging through chat.

---

## 3) Background runner + heartbeat logs

Long-running work should never be “just running.” It should emit durable evidence.

Create a repo-local structure:
- `logs/runner/`
- `logs/health/`
- `scripts/status/`

### Required scripts

#### `scripts/status/healthcheck.sh`
Runs:
- backend `/health`
- frontend HTTP check
- one real `POST /api/v1/analyze` smoke test with a fixed known-good address
- optional DB row-count checks

Outputs:
- human-readable log in `logs/health/`
- JSON summary to `docs/status/runtime-status.json`

#### `scripts/status/watchdog.sh`
Runs every 5–10 minutes and detects:
- process dead
- API unhealthy
- no new log activity for too long
- no completed action after N minutes

On failure it should:
- write a clear alert to `logs/health/`
- update `CURRENT_STATE.md` / `runtime-status.json`
- optionally trigger a cron delivery back to Discord

---

## 4) Session-safe execution protocol

Every work loop should follow this pattern:

1. read `CURRENT_STATE.md`
2. read `runtime-status.json`
3. inspect logs
4. verify current health with commands
5. do exactly one high-value fix
6. run verification
7. write updated state + next actions

That means even if chat context disappears, the repo still contains the truth.

---

## Recommended Daily Flow

### Start-of-session
1. read `docs/status/CURRENT_STATE.md`
2. read `docs/status/runtime-status.json`
3. run healthcheck
4. continue the highest-priority open fix

### During work
1. keep long tasks in background processes
2. log output to `logs/runner/`
3. update next-action queue when scope changes

### End-of-session
1. verify stack
2. update current state
3. record exact next action
4. ensure watchdog/cron is active

---

## Minimal implementation order

### Phase 1 — continuity first
1. create `docs/status/CURRENT_STATE.md`
2. create `docs/status/runtime-status.json`
3. create `scripts/status/healthcheck.sh`
4. create `scripts/status/watchdog.sh`

### Phase 2 — automation
5. schedule watchdog via cron every 5–10 min
6. send alerts to Discord/home channel
7. save rolling logs in `logs/health/`

### Phase 3 — execution discipline
8. require every session to update state files before stopping
9. require every production bug to leave behind:
   - test
   - log evidence
   - state update

---

## Concrete policy changes

### Policy A: no more chat-only state
If it matters, it goes in the repo.

### Policy B: no more silent long runs
If a process is running, it must produce:
- heartbeat
- logs
- last successful action
- last failed action

### Policy C: every pause includes a restart point
Before stopping, always write:
- current status
- exact next command
- exact next bug to fix

### Policy D: watchdog decides whether work is actually alive
Process existence is not enough. “Healthy” requires:
- service reachable
- smoke test passes or improves
- logs updating
- open issue queue progressing

---

## What this solves

This setup prevents:
- fake progress from zombie processes
- losing work when context compacts
- resuming cold with no idea what happened
- long pauses caused by unclear next action

It gives us:
- one canonical resume point
- proof of health
- automatic stall detection
- reliable handoff between sessions/agents

---

## Immediate next move

Implement Phase 1 in PlotLot now:
1. add durable status files
2. add healthcheck script
3. add watchdog script
4. wire a cron check-in to Discord or this thread
