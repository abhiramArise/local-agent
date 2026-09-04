"""
Tool registry: defines the schema for each tool the LLM can call.

This is what gets sent to Groq's API so the model knows what functions
exist, what parameters they take, and which parameters are required.

IMPORTANT: this schema is also what the (future) ambiguity-check layer
will use to decide if the LLM's proposed call is missing required info.
Keep "required" lists accurate — that's not cosmetic, it's load-bearing.
"""

FILE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a text file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to the file to read."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file at the given path. Overwrites if the file exists, creates it if not.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to the file to write."
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text content to write to the file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and folders inside a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to the directory to list."
                    }
                },
                "required": ["path"]
            }
        }
    }
]

SHELL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command on the local machine (PowerShell on Windows). "
                "The command runs inside the workspace folder as the working directory. "
                "Every command requires human confirmation before it runs, regardless of "
                "what it does — do not assume it will execute automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact shell command to run."
                    }
                },
                "required": ["command"]
            }
        }
    }
]

# Single source of truth the agent loop imports from.
ALL_TOOLS = FILE_TOOLS + SHELL_TOOLS
