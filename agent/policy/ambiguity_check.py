"""
Ambiguity check.

This is a code-level gate, not a prompt instruction. The LLM can be
told "ask if unsure" in the system prompt, but research shows models
are statistically biased toward guessing rather than pausing — so this
enforces it structurally instead of hoping the model complies.

Two checks, run before every tool call:

1. REQUIRED FIELD CHECK — does the call include every parameter the
   tool schema marks as required, with a non-empty value?

2. VAGUE REFERENCE CHECK — for path-like arguments, does the value
   look like a real filename, or a vague placeholder the model made up
   to avoid asking (e.g. "old_files", "the config", "temp")?

WHAT THIS DOES NOT DO:
- Understand semantic ambiguity ("delete the file the user mentioned
  earlier" — this won't catch reference ambiguity, only surface-level
  vagueness in the literal parameter value)
- Replace human judgment — it's a floor, not a ceiling
"""

import re

REQUIRED_PARAMS = {
    "read_file": ["path"],
    "write_file": ["path", "content"],
    "list_dir": ["path"],
}

VAGUE_PATTERNS = [
    r"^(the |a |an )?(old|new|recent|temp|some|all|any|other)([\s_-]?(file|files|folder|data|stuff))?$",
    r"^(that|this|it|the config|the file|the folder)$",
    r"^\.{2,}$",
    r"^$",
]

_VAGUE_RE = re.compile("|".join(VAGUE_PATTERNS), re.IGNORECASE)


def check_call(tool_name: str, args: dict) -> tuple:
    """
    Returns (ok: bool, reason: str).
    ok=False means: do NOT execute, ask the user/model to clarify instead.
    """
    required = REQUIRED_PARAMS.get(tool_name, [])

    for field in required:
        value = args.get(field)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return False, (
                f"'{tool_name}' requires '{field}', but it was missing or empty. "
                f"Ask the user to specify it rather than guessing."
            )

    path_value = args.get("path")
    if path_value and _VAGUE_RE.match(path_value.strip()):
        return False, (
            f"The path '{path_value}' looks like a vague placeholder, not a real "
            f"filename. Ask the user which specific file or folder they mean."
        )

    return True, ""