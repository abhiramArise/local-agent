"""
Rollback manager.

Before any state-changing action executes, this module saves enough
information to reverse it. Snapshots are stored on disk, keyed by the
audit log's entry_id, so a rollback snapshot and its audit entry can
always be cross-referenced.

WHAT THIS COVERS RIGHT NOW:
- write_file: snapshots the file's previous content (or "did not
  exist" if it's a new file) before the write happens.

WHAT THIS DOES NOT COVER YET:
- Shell commands (not built yet, per project scope)
- Deletes (no delete tool exists yet)
- Anything outside the workspace folder (file_tools.py already blocks
  this at the path level, so rollback never sees it)

Snapshot storage: agent/rollback/snapshots/<entry_id>.json
One file per action, so old snapshots can be pruned individually later
without touching others (not built yet — snapshots accumulate
indefinitely for now, worth knowing before running this for weeks).
"""

import os
import json
from datetime import datetime, timezone

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def _snapshot_path(entry_id: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{entry_id}.json")


def snapshot_before_write(entry_id: str, workspace_root: str, path: str) -> None:
    """
    Call this BEFORE write_file executes. Records whether the file
    existed and what it contained, so the write can be undone later.
    """
    full_path = os.path.abspath(os.path.join(workspace_root, path))
    existed = os.path.isfile(full_path)
    previous_content = None

    if existed:
        with open(full_path, "r", encoding="utf-8") as f:
            previous_content = f.read()

    snapshot = {
        "entry_id": entry_id,
        "action": "write_file",
        "path": path,
        "existed_before": existed,
        "previous_content": previous_content,
        "snapshotted_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(_snapshot_path(entry_id), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)


def rollback(entry_id: str, workspace_root: str) -> str:
    """
    Reverses the action recorded under entry_id. Returns a message
    describing what happened.

    For write_file: restores previous_content if the file existed
    before, or deletes the file if it didn't exist before (since the
    write created it from nothing).
    """
    snap_path = _snapshot_path(entry_id)
    if not os.path.exists(snap_path):
        return f"ERROR: no rollback snapshot found for entry_id '{entry_id}'"

    with open(snap_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    full_path = os.path.abspath(os.path.join(workspace_root, snapshot["path"]))

    if snapshot["existed_before"]:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(snapshot["previous_content"])
        return f"OK: restored '{snapshot['path']}' to its state before entry {entry_id}"
    else:
        if os.path.isfile(full_path):
            os.remove(full_path)
        return f"OK: removed '{snapshot['path']}' (it didn't exist before entry {entry_id})"


def list_rollbackable() -> list:
    """
    Returns entry_ids that have a snapshot available to roll back to,
    newest first. Useful for a 'what can I undo' view.
    """
    if not os.path.isdir(SNAPSHOT_DIR):
        return []
    files = [f[:-5] for f in os.listdir(SNAPSHOT_DIR) if f.endswith(".json")]
    files.sort(
        key=lambda entry_id: os.path.getmtime(_snapshot_path(entry_id)),
        reverse=True,
    )
    return files