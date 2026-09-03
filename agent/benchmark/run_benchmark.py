"""
Benchmark runner.

Usage:
    python benchmark/run_benchmark.py

Runs every task in tasks.py against the live agent, checks each
against real filesystem/audit-log state (not just the model's claimed
response), and saves a timestamped results file. Compares against the
most recent previous run so you can see if pass rate or behavior
changed — that's the actual point: catching drift, not just a one-time
pass/fail.

Results saved to: agent/benchmark/results/<timestamp>.json
"""

import sys
import os
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # agent/

from main import run_agent
from audit.signer import LOG_PATH
from tools.file_tools import WORKSPACE_ROOT
from llm_client import MODEL_NAME
from benchmark.tasks import TASKS

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def _read_log_lines():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _pair_new_entries(lines_before, lines_after):
    """
    Takes the raw new lines added during a task and pairs each
    "attempt" with its matching "outcome" (by entry_id), returning a
    flat list of merged dicts with action/params/status/summary.
    Unmatched outcomes (shouldn't normally happen) are skipped.
    """
    new_lines = lines_after[len(lines_before):]
    attempts = {e["id"]: e for e in new_lines if e.get("type") == "attempt"}
    outcomes = {e["entry_id"]: e for e in new_lines if e.get("type") == "outcome"}

    paired = []
    for entry_id, attempt in attempts.items():
        outcome = outcomes.get(entry_id, {})
        paired.append({
            "action": attempt.get("action"),
            "params": attempt.get("params"),
            "status": outcome.get("status", "unknown"),
            "summary": outcome.get("summary", ""),
        })
    return paired


def run_suite():
    print(f"Running {len(TASKS)} benchmark tasks against model: {MODEL_NAME}\n")
    results = []

    for t in TASKS:
        print(f"[{t['id']}] {t['prompt']}")
        lines_before = _read_log_lines()

        start = time.time()
        try:
            response_text = run_agent(t["prompt"]) or ""
        except Exception as e:
            response_text = ""
            print(f"    CRASHED: {type(e).__name__}: {e}")
        elapsed = round(time.time() - start, 2)

        lines_after = _read_log_lines()
        new_entries = _pair_new_entries(lines_before, lines_after)

        passed, detail = t["check"](WORKSPACE_ROOT, response_text, new_entries)
        status = "PASS" if passed else "FAIL"
        print(f"    {status} ({elapsed}s, {len(new_entries)} tool calls) — {detail}\n")

        results.append({
            "task_id": t["id"],
            "passed": passed,
            "detail": detail,
            "elapsed_seconds": elapsed,
            "tool_call_count": len(new_entries),
        })

    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL_NAME,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "results": results,
    }

    result_path = os.path.join(RESULTS_DIR, f"{int(time.time())}.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{summary['passed']}/{summary['total']} passed. Saved to {result_path}")
    _compare_to_previous(summary, result_path)


def _compare_to_previous(current_summary, current_path):
    """
    Finds the most recent PRIOR results file (not this run) and
    compares pass/fail per task. Flags anything that changed — this is
    the actual regression-detection part, not just a single pass/fail.
    """
    all_files = sorted(
        f for f in os.listdir(RESULTS_DIR)
        if f.endswith(".json") and os.path.join(RESULTS_DIR, f) != current_path
    )
    if not all_files:
        print("No previous run to compare against — this is the baseline.")
        return

    prev_path = os.path.join(RESULTS_DIR, all_files[-1])
    with open(prev_path, "r", encoding="utf-8") as f:
        prev_summary = json.load(f)

    prev_by_id = {r["task_id"]: r for r in prev_summary["results"]}
    changes = []
    for r in current_summary["results"]:
        prev = prev_by_id.get(r["task_id"])
        if prev and prev["passed"] != r["passed"]:
            direction = "REGRESSED" if prev["passed"] and not r["passed"] else "FIXED"
            changes.append(f"  {direction}: {r['task_id']}")

    print(f"\nCompared to previous run ({prev_summary['run_at']}, model: {prev_summary['model']}):")
    if changes:
        print("\n".join(changes))
    else:
        print("  No change in pass/fail status for any task.")


if __name__ == "__main__":
    run_suite()