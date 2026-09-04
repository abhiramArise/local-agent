"""
Ambiguity check.

This is a code-level gate, not a prompt instruction. The LLM can be
told "ask if unsure" in the system prompt, but research shows models
are statistically biased toward guessing rather than pausing — so this
enforces it structurally instead of hoping the model complies.

Three checks, run before every tool call:

1. REQUIRED FIELD CHECK — does the call include every parameter the
   tool schema marks as required, with a non-empty value?

2. VAGUE REFERENCE CHECK — for path-like arguments, does the value
   look like a real filename, or a vague placeholder the model made up
   (e.g. "old_files", "the config", "temp")?

3. REQUEST GROUNDING CHECK — for write_file specifically, does the
   user's ORIGINAL request actually contain any real information (a
   filename, a topic, a subject) for the model to have worked from? A
   request like "create a file with some text" gives the model
   nothing to go on — any filename and content it picks is invented,
   not vague-looking in isolation (a filename like "sample.txt" passes
   check 2 easily), but still a pure guess. This check catches that by
   looking at whether the SOURCE request had any real content, not by
   judging the model's output value in isolation.

WHAT THIS DOES NOT DO:
- Understand deep semantic grounding (e.g. confirming a filename the
  model chose is really the best interpretation of a detailed request)
  — check 3 is a floor (did the user give ANYTHING to work with), not
  a full semantic match
- Replace human judgment — it's a floor, not a ceiling
"""

import re

REQUIRED_PARAMS = {
    "read_file": ["path"],
    "write_file": ["path", "content"],
    "list_dir": ["path"],
    "run_shell": ["command"],
    "browser_navigate": ["url"],
    "browser_click": ["selector"],
    "browser_fill": ["selector", "text"],
}

VAGUE_PATTERNS = [
    r"^(the |a |an )?(old|new|recent|temp|some|all|any|other)([\s_-]?(file|files|folder|data|stuff))?$",
    r"^(that|this|it|the config|the file|the folder)$",
    r"^\.{2,}$",  # just dots, no real path
    r"^$",         # empty
]

_VAGUE_RE = re.compile("|".join(VAGUE_PATTERNS), re.IGNORECASE)

# Words that carry no real information about WHAT the file should be
# named or contain — generic task/control vocabulary. If a request,
# after stripping these, has fewer than MIN_MEANINGFUL_WORDS left,
# treat it as ungrounded: the user didn't actually specify anything
# for the model to base a filename or content on.
_REQUEST_STOPWORDS = {
    "create", "make", "write", "add", "generate", "produce",
    "file", "files", "text", "content", "data", "document",
    "some", "any", "a", "an", "the", "with", "for", "of", "to", "in",
    "on", "and", "or", "please", "can", "you", "new", "it", "that",
    "this", "called", "named", "titled", "me", "my", "i", "want",
    "would", "like", "just", "into",
}
MIN_MEANINGFUL_WORDS = 1


def _meaningful_word_count(text: str) -> int:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    meaningful = [w for w in words if w not in _REQUEST_STOPWORDS and len(w) > 2]
    return len(meaningful)


def check_call(tool_name: str, args: dict, user_request: str = "") -> tuple:
    """
    Returns (ok: bool, reason: str).
    ok=False means: do NOT execute, ask the user/model to clarify instead.
    user_request is the ORIGINAL request text this call is responding
    to — used for check 3. Optional; if omitted, check 3 is skipped.
    """
    required = REQUIRED_PARAMS.get(tool_name, [])

    # Check 1: required fields present and non-empty
    for field in required:
        value = args.get(field)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return False, (
                f"'{tool_name}' requires '{field}', but it was missing or empty. "
                f"Ask the user to specify it rather than guessing."
            )

    # Check 2: vague path-like values
    path_value = args.get("path")
    if path_value and _VAGUE_RE.match(path_value.strip()):
        return False, (
            f"The path '{path_value}' looks like a vague placeholder, not a real "
            f"filename. Ask the user which specific file or folder they mean."
        )

    # Check 3: does the original request actually contain any real
    # information, or is the model inventing a filename/content from
    # nothing? Only applies to write_file — read_file/list_dir don't
    # involve the model choosing new content.
    if tool_name == "write_file" and user_request:
        if _meaningful_word_count(user_request) < MIN_MEANINGFUL_WORDS:
            return False, (
                f"The request '{user_request}' doesn't specify a filename or "
                f"subject/content for the file. The model would have to invent "
                f"both. Ask the user what the file should be named and contain."
            )

    return True, ""