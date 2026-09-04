"""
Agent loop — SKELETON STAGE.

This proves the core pipeline works: LLM proposes a tool call, we
execute it, feed the result back, repeat until the model gives a
final text answer.

What's intentionally NOT here yet (later build steps):
- Ambiguity check (blocking on missing/vague params)
- Preview/diff before execution
- Signing + audit log
- Rollback snapshots
- Session checkpoint/resume

Do not point this at anything you're not comfortable having written to
directly — it executes file writes with no safety net beyond the
workspace path confinement in file_tools.py.
"""

import json
import uuid
from llm_client import call_llm, MODEL_NAME
from tools.registry import ALL_TOOLS
from tools.file_tools import TOOL_DISPATCH as FILE_TOOL_DISPATCH
from tools.shell_tools import SHELL_TOOL_DISPATCH
from audit.signer import log_action, log_outcome
from rollback.undo_manager import snapshot_before_write
from tools.file_tools import WORKSPACE_ROOT
from policy.ambiguity_check import check_call
from state.session import save_checkpoint, mark_completed, find_resumable, load_checkpoint

TOOL_DISPATCH = {**FILE_TOOL_DISPATCH, **SHELL_TOOL_DISPATCH}

MAX_STEPS = 10  # hard cap so a bad loop can't run forever
SESSION_ID = str(uuid.uuid4())[:8]  # one id per run of this script


def run_agent(user_request: str = None, resume_task_id: str = None, resume_messages: list = None):
    """
    Either starts a fresh task (pass user_request) or resumes an
    interrupted one (pass resume_task_id + resume_messages, loaded
    from a checkpoint by the caller).
    """
    if resume_messages is not None:
        task_id = resume_task_id
        messages = resume_messages
        print(f"Resuming task {task_id} from checkpoint ({len(messages)} messages)...")
        original_request = next(
            (m["content"] for m in messages if m.get("role") == "user"), ""
        )
    else:
        task_id = str(uuid.uuid4())[:8]
        original_request = user_request
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a local assistant with file access (read_file, "
                    "write_file, list_dir) and shell command access (run_shell). "
                    "Every shell command requires human confirmation before it "
                    "runs — expect that some commands may be declined or blocked. "
                    "Only operate within the workspace folder."
                ),
            },
            {"role": "user", "content": user_request},
        ]

    for step in range(MAX_STEPS):
        print(f"\n--- Step {step + 1} ---")
        response = call_llm(messages, ALL_TOOLS)

        # No tool call — model gave a final answer, we're done.
        if not response.tool_calls:
            print(f"\nFinal answer:\n{response.content}")
            messages.append({"role": "assistant", "content": response.content})
            save_checkpoint(task_id, messages, status="completed")
            mark_completed(task_id)
            return response.content

        # Append the assistant's tool-call request to history.
        messages.append(response)

        # Execute each requested tool call.
        for tool_call in response.tool_calls:
            tool_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                result = f"ERROR: model sent malformed arguments: {tool_call.function.arguments}"
                args = {}
            else:
                print(f"Calling {tool_name}({args})")

                # Ambiguity check runs BEFORE logging/execution. A
                # blocked call is still logged — "the model tried this
                # and was blocked" is itself worth having on record.
                ok, reason = check_call(tool_name, args, user_request=original_request)

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
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )
                    continue

                func = TOOL_DISPATCH.get(tool_name)
                if func is None:
                    result = f"ERROR: unknown tool '{tool_name}'"
                    log_outcome(entry_id, status="error", summary=result)
                else:
                    # Snapshot BEFORE executing any write, so it can be
                    # undone even if something goes wrong right after.
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
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )

        # Checkpoint after every step — if the process dies on the
        # NEXT call_llm (crash, throttle, network drop), this step's
        # progress is still on disk.
        save_checkpoint(task_id, messages, status="in_progress")

    print("\nMAX_STEPS reached without a final answer. Stopping.")
    save_checkpoint(task_id, messages, status="in_progress")
    return None


if __name__ == "__main__":
    print("Local Agent — skeleton stage (file tools only)")

    resumable = find_resumable()
    if resumable:
        print(f"\nFound {len(resumable)} interrupted task(s) from previous runs:")
        for task_id, updated_at in resumable:
            print(f"  {task_id}  (last updated {updated_at})")
        choice = input("\nResume the most recent one? (y/n): ").strip().lower()
        if choice == "y":
            task_id, _ = resumable[0]
            saved_messages = load_checkpoint(task_id)
            run_agent(resume_task_id=task_id, resume_messages=saved_messages)

    print("\nType your request, or 'quit' to exit.\n")
    while True:
        user_input = input("> ")
        if user_input.strip().lower() in ("quit", "exit"):
            break
        run_agent(user_input)