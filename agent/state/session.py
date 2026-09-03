"""
Session checkpoint/resume.

Saves the full conversation state to disk after every step. If the
process crashes, gets rate-limited, or you close the terminal by
accident, you can resume from the last checkpoint instead of losing
everything and starting the task over.

Checkpoint file: agent/state/checkpoints/<session_id>.json

DESIGN NOTE ON SERIALIZATION:
The Groq SDK returns assistant messages as SDK objects (not plain
dicts) when they contain tool_calls. Those objects aren't directly
JSON-serializable. This module converts them to plain dicts before
saving (using .model_dump() if available, since the Groq SDK is
pydantic-based) and stores everything as plain dicts — which is also
exactly the format the Groq API accepts back in, so a resumed
conversation round-trips cleanly.
"""

import json
import os
from datetime import datetime, timezone

CHECKPOINT_DIR = os.path.join(os.path.dirname(__file__), "checkpoints")
os.makedirs(CHECKPOINT_DIR, exist_ok=True)


def _checkpoint_path(session_id: str) -> str:
    return os.path.join(CHECKPOINT_DIR, f"{session_id}.json")


def _to_plain_dict(message):
    """
    Converts a message to a plain dict, whether it's already a dict
    (our own 'user'/'tool' messages) or an SDK object (assistant
    responses with tool_calls).
    """
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    # Fallback: best-effort attribute extraction if the SDK shape changes.
    return {"role": getattr(message, "role", "assistant"),
             "content": getattr(message, "content", None)}


def save_checkpoint(session_id: str, messages: list, status: str = "in_progress") -> None:
    """
    Call this after every step of the agent loop. Overwrites the
    previous checkpoint for this session_id — we only need the latest
    state, not a history of every intermediate step.
    """
    checkpoint = {
        "session_id": session_id,
        "status": status,  # "in_progress" or "completed"
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "messages": [_to_plain_dict(m) for m in messages],
    }
    with open(_checkpoint_path(session_id), "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)


def load_checkpoint(session_id: str):
    """
    Returns the saved messages list for a session, or None if no
    checkpoint exists.
    """
    path = _checkpoint_path(session_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)
    return checkpoint["messages"]


def mark_completed(session_id: str) -> None:
    """
    Call this when a task finishes normally (model gave a final
    answer, no more tool calls). Keeps the checkpoint on disk but
    marks it done, so find_resumable() won't offer to resume it.
    """
    path = _checkpoint_path(session_id)
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)
    checkpoint["status"] = "completed"
    checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)


def find_resumable() -> list:
    """
    Returns a list of (session_id, updated_at) for sessions that are
    still "in_progress" — i.e. didn't finish cleanly, likely due to a
    crash or interruption. Newest first.
    """
    if not os.path.isdir(CHECKPOINT_DIR):
        return []

    resumable = []
    for fname in os.listdir(CHECKPOINT_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(CHECKPOINT_DIR, fname), "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
        if checkpoint.get("status") == "in_progress":
            resumable.append((checkpoint["session_id"], checkpoint["updated_at"]))

    resumable.sort(key=lambda x: x[1], reverse=True)
    return resumable