"""
Rollback CLI — undo a past write_file action.

Deliberately NOT something the agent/LLM can trigger on its own.
Undo is a human decision, invoked by a human, on purpose. Run this
directly:

    python rollback_cli.py --list              # see what can be undone
    python rollback_cli.py --undo <entry_id>    # undo a specific action
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from rollback.undo_manager import list_rollbackable, rollback
from tools.file_tools import WORKSPACE_ROOT
from audit.signer import log_action, log_outcome


def main():
    if "--list" in sys.argv:
        entries = list_rollbackable()
        if not entries:
            print("Nothing available to roll back yet.")
            return
        print(f"{len(entries)} rollbackable actions (newest first):\n")
        for entry_id in entries:
            print(f"  {entry_id}")
        print("\nRun: python rollback_cli.py --undo <entry_id>")
        return

    if "--undo" in sys.argv:
        idx = sys.argv.index("--undo")
        if idx + 1 >= len(sys.argv):
            print("ERROR: --undo requires an entry_id, e.g. --undo 479a471f")
            return
        entry_id = sys.argv[idx + 1]

        confirm = input(f"Roll back action {entry_id}? This will overwrite/remove "
                         f"the current file. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Cancelled.")
            return

        result = rollback(entry_id, WORKSPACE_ROOT)
        print(result)

        rollback_entry_id = log_action(
            action="rollback",
            params={"undoing_entry_id": entry_id},
            model="human_operator",
            session_id="manual_rollback",
        )
        log_outcome(
            entry_id=rollback_entry_id,
            status="success" if result.startswith("OK") else "error",
            summary=result,
        )
        return

    print(__doc__)


if __name__ == "__main__":
    main()