# Local-Agent

An LLM-backed agent with real file-system access on Windows, built around one idea: most AI agent complaints in 2026 aren't about capability, they're about trust. Users don't know what an agent actually did, can't undo mistakes, and get forced guesses instead of clarifying questions when instructions are ambiguous. This project treats those three problems as hard constraints enforced in code, not suggestions made to the model.

Author: Abhi (github.com/abhiramArise)
Status: Core build complete, all 7 planned components implemented and tested

---

## What this is

An agent that reads, writes, and lists files on request, using Groq (`openai/gpt-oss-120b`) for reasoning. What makes it different from just wiring an LLM to file I/O is everything that sits between the model's decision and the actual execution:

- **Nothing executes without being logged first**, and the log is tamper-evident
- **Every file write can be undone**, with a snapshot taken before the write happens
- **The agent cannot guess when it's missing information** — this is enforced by code, not by asking the model nicely
- **A crashed or interrupted task can be resumed** from exactly where it left off
- **A regression benchmark suite** catches silent behavior changes over time — the same model can behave differently from one day to the next, and this project has direct evidence of that happening

---

## Architecture

```
agent/
├── main.py                    # agent loop — orchestrates everything below
├── llm_client.py               # Groq API wrapper
├── tools/
│   ├── registry.py              # tool schemas for function calling
│   └── file_tools.py            # read_file, write_file, list_dir (path-confined to workspace/)
├── audit/
│   └── signer.py                 # tamper-evident, append-only action log
├── rollback/
│   └── undo_manager.py           # snapshot + restore for every write
├── policy/
│   └── ambiguity_check.py        # blocks execution on missing/vague/ungrounded requests
├── state/
│   └── session.py                 # checkpoint/resume for interrupted tasks
├── benchmark/
│   ├── tasks.py                   # fixed regression test set
│   └── run_benchmark.py           # runs the suite, diffs against the previous run
└── rollback_cli.py              # human-only undo trigger (deliberately not agent-callable)
```

## Execution pipeline

Every tool call the model proposes goes through this sequence, no exceptions:

```
LLM proposes tool call
    ↓
Ambiguity check — missing param, vague value, or ungrounded request? → BLOCKED, logged, model asked to clarify
    ↓
Action logged (hash, timestamp, params, model version) — BEFORE execution
    ↓
Snapshot taken (if it's a write) — BEFORE execution
    ↓
Executed
    ↓
Outcome logged (success/error/blocked) — AFTER execution, as a separate linked entry
    ↓
Checkpoint saved — state survives a crash on the NEXT step
    ↓
Result returned to LLM
```

---

## What was actually tested, and what broke

This section is the part that matters most for a portfolio piece: not "I built X," but "I built X, tested it against real behavior, found real bugs, and fixed them."

### Bug 1: The ambiguity check had a real blind spot

The initial ambiguity check caught vague-*looking* values (like a filename literally called "old_files") but not confident, plausible-looking guesses. Given the prompt "create a file with some text" — deliberately giving the model nothing to work with — the model would sometimes invent a filename like `sample.txt` and made-up content, and nothing about that filename looks wrong in isolation. It passed the vague-pattern check easily.

**Fix:** added a request-grounding check that looks at the *source* request, not just the model's output. If the user's original message contains no real information (no filename, no topic, stripped of generic task vocabulary), the call is blocked regardless of how plausible the model's invented value looks. This was verified directly — the regression benchmark caught the model attempting this exact failure (inventing `sample.txt`, then `example.txt` on a later run) and the fix blocked both correctly.

### Bug 2: Audit log only recorded intent, not outcome

Initial version logged the attempt before execution but never recorded whether it actually succeeded or failed. A blocked path-traversal attempt looked identical in the log to a successful read. Fixed by adding a linked "outcome" entry, written after execution completes, so the log answers "what happened," not just "what was tried."

### Finding: the model is measurably non-deterministic

Running the identical prompt ("create a file with some text") across different benchmark runs produced different behaviors: sometimes the model asked a clarifying question in plain text before attempting anything, other times it directly attempted a tool call with an invented filename. Same model, same prompt, different behavior seconds apart. This is direct, first-hand evidence of the "silent model regression / inconsistent behavior" problem this project set out to defend against — not a hypothetical, something actually observed and logged.

### Verified end-to-end (not just written, actually run and confirmed)

- **Audit trail**: tamper-evident hash verification passed after every test round, including after a deliberate path-traversal attempt
- **Rollback**: a file was written, overwritten, then successfully restored to its pre-overwrite state via `rollback_cli.py`, with the rollback itself appearing as its own signed audit entry
- **Session resume**: a task's full conversation state was saved mid-run, the process was restarted, and the agent correctly resumed from the saved checkpoint with full context intact
- **Regression benchmark**: 6/6 tasks passing consistently across three separate runs after the ambiguity-check fix, including direct evidence of the fix working against real (not simulated) model guessing behavior

---

## Known limitations (stated honestly, not hidden)

- **The audit log only sees what the model actually attempts.** If the model refuses a request in plain text without ever calling a tool, nothing is logged. The log is a record of attempted actions, not a complete record of every prompt sent to the model.
- **The ambiguity check's request-grounding check is a heuristic**, not a semantic understanding of the request. It catches requests with zero real information, but a request with *some* misleading information could still slip through.
- **Rollback currently only covers `write_file`.** There's no delete tool yet, so nothing needed rollback beyond overwrite/create.
- **Not fully offline.** Reasoning calls go to Groq's API — this is "local execution, cloud reasoning," not zero-network-dependency. This was a deliberate scoping decision after evaluating the laptop's hardware (7.7GB RAM, 2GB VRAM — insufficient for reliable local tool-calling).
- **Snapshots and checkpoints accumulate indefinitely** on disk — no pruning implemented yet.

---

## Stack

- Python
- Groq API (`openai/gpt-oss-120b`) for reasoning — Groq's Llama models were deprecated mid-project; this is itself a small real-world example of the "model availability changes without much warning" problem
- No external dependencies beyond the `groq` SDK — audit logging, rollback, and checkpointing are all plain Python + JSON, no database

## Setup

See `SETUP.md` for full instructions. Quick version:
```powershell
pip install -r requirements.txt
$env:GROQ_API_KEY = "your-key-here"
cd agent
python main.py
```

To run the regression suite:
```powershell
python benchmark/run_benchmark.py
```

To undo a past write:
```powershell
python rollback_cli.py --list
python rollback_cli.py --undo <entry_id>
```