"""
Agent loop.

CONVERSATION MODEL: one continuous conversation per run of this script,
made up of multiple TURNS. A turn starts when you type a line at the
'>' prompt and ends when the model gives a final text answer (or hits
MAX_STEPS_PER_TURN). The full message history persists across turns,
in the same list, for the whole session — so if the model asks "would
you like me to proceed?", your next line is a real reply to that
question, not a new, contextless conversation.

This matters in practice: the model used in this project frequently
asks for confirmation in plain text before calling a consequential
tool (shell commands, browser actions), regardless of instructions
telling it to call the tool directly. Earlier versions of this loop
started a brand-new conversation on every line of input, which meant
a "yes" typed in reply to the model's question was meaningless — the
model had never seen the question in that context. This version fixes
that by keeping one shared `messages` list across the whole session.

Crash recovery (state/session.py) still checkpoints after every step,
using ONE task_id for the entire session rather than one per turn, so
a crash mid-conversation resumes the whole thing, not just the last line.
"""

import json
import uuid
from llm_client import call_llm, MODEL_NAME
from tools.registry import ALL_TOOLS
from tools.file_tools import TOOL_DISPATCH as FILE_TOOL_DISPATCH
from tools.shell_tools import SHELL_TOOL_DISPATCH
from tools.browser_tools import BROWSER_TOOL_DISPATCH
from audit.signer import log_action, log_outcome
from rollback.undo_manager import snapshot_before_write
from tools.file_tools import WORKSPACE_ROOT
from policy.ambiguity_check import check_call
from state.session import save_checkpoint, mark_completed, find_resumable, load_checkpoint

TOOL_DISPATCH = {**FILE_TOOL_DISPATCH, **SHELL_TOOL_DISPATCH, **BROWSER_TOOL_DISPATCH}

MAX_STEPS_PER_TURN = 10  # cap on tool-call round-trips within a SINGLE turn
SESSION_ID = str(uuid.uuid4())[:8]  # for audit log attribution, unrelated to task_id

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are a local assistant with file access (read_file, "
        "write_file, list_dir), shell command access (run_shell), "
        "and browser access (browser_navigate, browser_click, "
        "browser_fill, browser_read). Shell and browser actions "
        "(except browser_read) require human confirmation before "
        "they run — expect some may be declined. Browser actions "
        "cannot be undone once confirmed. Only operate within the "
        "workspace folder for file operations. When you ask the user "
        "a yes/no confirmation question, their next message IS the "
        "answer to that question — treat it as such rather than "
        "asking again from scratch."
    ),
}


def run_turn(task_id: str, messages: list, current_user_request: str):
    """
    Runs the tool-calling loop for ONE turn: repeatedly calls the LLM
    and executes any tool calls it requests, until the model returns a
    final text answer (no tool_calls) or MAX_STEPS_PER_TURN is hit.

    Mutates `messages` in place by appending to it — the caller's list
    IS the conversation history, shared across turns.

    current_user_request is the text of THIS turn's user message, used
    by the ambiguity check's request-grounding check (check 3 in
    ambiguity_check.py) — grounding is checked against what the user
    just asked, not the very first message of the whole session.

    Returns the final answer text, or None if MAX_STEPS_PER_TURN was
    reached without one.
    """
    for step in range(MAX_STEPS_PER_TURN):
        print(f"\n--- Step {step + 1} ---")
        response = call_llm(messages, ALL_TOOLS)

        if not response.tool_calls:
            print(f"\nFinal answer:\n{response.content}")
            messages.append({"role": "assistant", "content": response.content})
            save_checkpoint(task_id, messages, status="completed")
            mark_completed(task_id)
            return response.content

        messages.append(response)

        for tool_call in response.tool_calls:
            tool_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                result = f"ERROR: model sent malformed arguments: {tool_call.function.arguments}"
                args = {}
            else:
                print(f"Calling {tool_name}({args})")

                ok, reason = check_call(tool_name, args, user_request=current_user_request)

                entry_id = log_action(
                    action=tool_name,
                    params=args,
                    model=MODEL_NAME,
                    session_id=SESSION_ID,
                )

                if not ok:
                    result = f"BLOCKED: {reason}"
                    log_outcome(entry_id, status="blocked", summary=result)
                    print(f"Logged as {entry_id}")
                    print(f"Result: {result}")
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                    )
                    continue

                func = TOOL_DISPATCH.get(tool_name)
                if func is None:
                    result = f"ERROR: unknown tool '{tool_name}'"
                    log_outcome(entry_id, status="error", summary=result)
                else:
                    if tool_name == "write_file" and "path" in args:
                        snapshot_before_write(entry_id, WORKSPACE_ROOT, args["path"])

                    try:
                        result = func(**args)
                        status = "error" if str(result).startswith("ERROR") else "success"
                        log_outcome(entry_id, status=status, summary=str(result))
                    except Exception as e:
                        result = f"ERROR: {type(e).__name__}: {e}"
                        log_outcome(entry_id, status="error", summary=result)

                print(f"Logged as {entry_id}")

            print(f"Result: {result}")
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": str(result)}
            )

        save_checkpoint(task_id, messages, status="in_progress")

    print("\nMAX_STEPS_PER_TURN reached without a final answer this turn.")
    save_checkpoint(task_id, messages, status="in_progress")
    return None


if __name__ == "__main__":
    print("Local Agent")

    task_id = str(uuid.uuid4())[:8]
    messages = [SYSTEM_PROMPT]

    resumable = find_resumable()
    if resumable:
        print(f"\nFound {len(resumable)} interrupted session(s) from previous runs:")
        for rid, updated_at in resumable:
            print(f"  {rid}  (last updated {updated_at})")
        choice = input("\nResume the most recent one? (y/n): ").strip().lower()
        if choice == "y":
            task_id, _ = resumable[0]
            messages = load_checkpoint(task_id)
            print(f"Resumed session {task_id} with {len(messages)} prior messages.")

    print("\nType your request, or 'quit' to exit. The conversation persists "
          "across turns — if the agent asks you a question, your next "
          "message is treated as the answer.\n")

    while True:
        user_input = input("> ")
        if user_input.strip().lower() in ("quit", "exit"):
            break

        messages.append({"role": "user", "content": user_input})

        try:
            run_turn(task_id, messages, current_user_request=user_input)
        except Exception as e:
            print(f"\nERROR: this turn failed: {type(e).__name__}: {e}")
            print("The conversation history is preserved — you can try again.\n")