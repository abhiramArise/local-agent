"""
Audit signing layer.

Every tool call gets recorded here BEFORE it executes: what was
requested, when, by which model, with what parameters. Each entry is
hashed so you (or anyone) can verify the log wasn't edited after the
fact — that's what "signed" means here (see note below on what this
does and doesn't guarantee).

Log file: agent/audit/audit_log.jsonl (append-only, one JSON object
per line, never overwritten or edited in place).

WHAT THIS SIGNING ACTUALLY GUARANTEES (be precise about this):
- Each entry's hash is computed from its own content, so if someone
  edits a past line, that line's hash won't match anymore — tampering
  with a single entry is detectable.
- It does NOT use real cryptographic signing (no private key, no
  asymmetric crypto) — this is a local integrity hash, not a legal
  signature. Don't oversell this in your pitch as "cryptographically
  signed" in the security sense; call it "hash-verified" or
  "tamper-evident" to be accurate. Upgrading to real signing (e.g.
  with a local keypair) is a reasonable v2 step, not done here.
- It does NOT protect against someone deleting the whole log file or
  rewriting it entirely from scratch — only against silently editing
  one entry while leaving the rest intact.
"""

import json
import hashlib
import os
from datetime import datetime, timezone

AUDIT_DIR = os.path.join(os.path.dirname(__file__))
LOG_PATH = os.path.join(AUDIT_DIR, "audit_log.jsonl")


def _hash_entry(entry: dict) -> str:
    """
    Hash the entry's content (everything except the hash field itself)
    so tampering with any field after the fact is detectable.
    """
    serialized = json.dumps(entry, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def log_action(action: str, params: dict, model: str, session_id: str) -> str:
    """
    Records an action BEFORE execution. Returns the entry's id so the
    caller can reference it later (e.g. for a rollback snapshot, or
    to log the outcome once execution finishes).
    """
    entry = {
        "type": "attempt",
        "id": hashlib.sha256(
            f"{action}{params}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "params": params,
        "model": model,
        "session_id": session_id,
    }
    entry["content_hash"] = _hash_entry(entry)

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return entry["id"]


def log_outcome(entry_id: str, status: str, summary: str) -> None:
    """
    Records what actually happened for a given action, AFTER execution.

    Written as a separate append-only entry (never edits the original
    "attempt" line — that would break tamper-evidence). Links back via
    entry_id so the two can be read together.

    status should be "success" or "error".
    summary is a short string — the tool's return value or error message.
    """
    outcome = {
        "type": "outcome",
        "entry_id": entry_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "summary": summary[:300],
    }
    outcome["content_hash"] = _hash_entry(outcome)

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(outcome) + "\n")


def verify_log() -> tuple[bool, list]:
    """
    Re-checks every entry's hash against its content. Returns
    (all_valid, list_of_problem_entry_ids). Run this any time you want
    to confirm the log hasn't been tampered with since it was written.
    Works across both "attempt" and "outcome" entry types.
    """
    if not os.path.exists(LOG_PATH):
        return True, []

    problems = []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            entry = json.loads(line)
            claimed_hash = entry.pop("content_hash", None)
            actual_hash = _hash_entry(entry)
            if claimed_hash != actual_hash:
                label = entry.get("id") or entry.get("entry_id") or f"line_{line_num}"
                problems.append(label)

    return len(problems) == 0, problems