"""
View and verify the audit log.

Usage:
    python view_audit_log.py            # print all entries, readable
    python view_audit_log.py --verify   # check log integrity only
"""

import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from audit.signer import LOG_PATH, verify_log


def print_log():
    if not os.path.exists(LOG_PATH):
        print("No audit log yet — run the agent and perform an action first.")
        return

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f]

    if not entries:
        print("Audit log is empty.")
        return

    attempts = {e["id"]: e for e in entries if e.get("type") == "attempt"}
    outcomes = {e["entry_id"]: e for e in entries if e.get("type") == "outcome"}

    print(f"{len(attempts)} logged actions:\n")
    for entry_id, e in attempts.items():
        outcome = outcomes.get(entry_id)
        print(f"[{entry_id}] {e['timestamp']}")
        print(f"    session: {e['session_id']}  model: {e['model']}")
        print(f"    action:  {e['action']}({e['params']})")
        if outcome:
            print(f"    status:  {outcome['status'].upper()} — {outcome['summary']}")
        else:
            print(f"    status:  UNKNOWN (no outcome recorded — process may have crashed mid-execution)")
        print()


if __name__ == "__main__":
    if "--verify" in sys.argv:
        valid, problems = verify_log()
        if valid:
            print("Audit log integrity check: PASSED. No tampering detected.")
        else:
            print(f"Audit log integrity check: FAILED. Problem entries: {problems}")
    else:
        print_log()