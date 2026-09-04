"""
Shell command tool.

APPROACH: blocklist (not whitelist), by explicit choice. This is the
higher-risk option compared to a whitelist, and that tradeoff is
accepted deliberately here — see README for the reasoning. Because a
blocklist can NEVER be complete (there is always some destructive
pattern nobody thought to add), the blocklist is NOT the real safety
mechanism. The real safety mechanism is the mandatory human
confirmation prompt before every single command runs, blocklisted or
not. Do not treat the blocklist as sufficient on its own.

Commands run with cwd set to the workspace folder, but this does NOT
sandbox them the way file_tools.py's path checks do — a shell command
can still reference absolute paths outside the workspace. This is a
real, accepted limitation, not an oversight.
"""

import subprocess
import re
import os

from tools.file_tools import WORKSPACE_ROOT

BLOCKLIST_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdel\s+/f\b.*\b/s\b",
    r"\brmdir\s+/s\b",
    r"\bformat\s+[a-zA-Z]:",
    r"\bdiskpart\b",
    r"\bshutdown\b",
    r"\brestart-computer\b",
    r"\bstop-computer\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;\s*:",
    r"\btaskkill\s+/f\s+/im\s+\*",
    r"\breg\s+delete\b",
    r"\bremove-item\b.*-recurse.*-force",
    r"\bnetsh\b",
    r"\bchmod\s+777\s+/\b",
    r"\bpowershell\b.*-enc(odedcommand)?\b",
    r"curl\s+.*\|\s*(bash|sh)\b",
    r"wget\s+.*\|\s*(bash|sh)\b",
]

_BLOCK_RE = re.compile("|".join(BLOCKLIST_PATTERNS), re.IGNORECASE)

TIMEOUT_SECONDS = 30


def run_shell(command: str) -> str:
    """
    Checks the command against the blocklist, then ALWAYS asks for
    human confirmation before running anything that passes.

    Runs via PowerShell explicitly (not the default cmd.exe that
    subprocess.run(shell=True) uses on Windows).
    """
    if _BLOCK_RE.search(command):
        return f"BLOCKED: command matches a known-dangerous pattern and was not run: {command}"

    print(f"\n[SHELL] The agent wants to run: {command}")
    confirm = input("Allow this command to run? Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        return f"CANCELLED: user declined to run: {command}"

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        output = result.stdout.strip()
        error = result.stderr.strip()
        summary = f"exit code {result.returncode}"
        if output:
            summary += f"\nstdout:\n{output[:2000]}"
        if error:
            summary += f"\nstderr:\n{error[:2000]}"
        return summary
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {TIMEOUT_SECONDS}s: {command}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


SHELL_TOOL_DISPATCH = {
    "run_shell": run_shell,
}