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
from tools.file_tools import TOOL_DISPATCH
from audit.signer import log_action, log_outcome
from rollback.undo_manager import snapshot_before_write
from tools.file_tools import WORKSPACE_ROOT
from policy.ambiguity_check import check_call

MAX_STEPS = 10  # hard cap so a bad loop can't run forever
SESSION_ID = str(uuid.uuid4())[:8]  # one id per run of this script


def run_agent(user_request: str):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a local file assistant. You can read, write, and "
                "list files using the tools available to you. Use them when "
                "needed. Only operate within the workspace folder."
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

                ok, reason = check_call(tool_name, args)

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

    print("\nMAX_STEPS reached without a final answer. Stopping.")
    return None


if __name__ == "__main__":
    print("Local Agent — skeleton stage (file tools only)")
    print("Type your request, or 'quit' to exit.\n")
    while True:
        user_input = input("> ")
        if user_input.strip().lower() in ("quit", "exit"):
            break
        run_agent(user_input)