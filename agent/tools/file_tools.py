"""
File tool implementations.

Skeleton stage: no audit log, no rollback, no ambiguity check yet.
Those wrap around these functions in later steps — this file just
needs to execute correctly and safely (path-confined) on its own.

Safety note: every path is resolved against WORKSPACE_ROOT and checked
to make sure it doesn't escape that folder. This is a minimum bar, not
a full sandbox — don't treat this as safe to point at your whole
filesystem yet.
"""

import os

# Confine all file operations to this folder for now.
# Change this to whatever project folder you want the agent to work in.
WORKSPACE_ROOT = os.path.abspath("./workspace")
os.makedirs(WORKSPACE_ROOT, exist_ok=True)


def _resolve_safe_path(path: str) -> str:
    """
    Resolve a path relative to WORKSPACE_ROOT and reject anything
    that tries to escape it (e.g. '../../etc/passwd').
    """
    full_path = os.path.abspath(os.path.join(WORKSPACE_ROOT, path))
    if not full_path.startswith(WORKSPACE_ROOT):
        raise PermissionError(
            f"Path '{path}' resolves outside the allowed workspace "
            f"({WORKSPACE_ROOT}). Refusing to proceed."
        )
    return full_path


def read_file(path: str) -> str:
    safe_path = _resolve_safe_path(path)
    if not os.path.isfile(safe_path):
        return f"ERROR: file not found at '{path}'"
    with open(safe_path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    safe_path = _resolve_safe_path(path)
    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
    with open(safe_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"OK: wrote {len(content)} chars to '{path}'"


def list_dir(path: str) -> str:
    safe_path = _resolve_safe_path(path)
    if not os.path.isdir(safe_path):
        return f"ERROR: '{path}' is not a directory"
    entries = os.listdir(safe_path)
    if not entries:
        return f"'{path}' is empty"
    return "\n".join(entries)


# Maps tool name (as declared in registry.py) to the actual function.
# main.py uses this to dispatch a tool call from the LLM to real code.
TOOL_DISPATCH = {
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
}
