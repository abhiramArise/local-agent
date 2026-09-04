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

BROWSER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate a real browser to a URL. Requires human confirmation before running — cannot be undone.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The full URL to navigate to."}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element on the current page by CSS selector. Requires human confirmation — cannot be undone (may submit forms, trigger purchases, etc.).",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string", "description": "CSS selector of the element to click."}},
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Type text into a form field on the current page by CSS selector. Requires human confirmation — cannot be undone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the input field."},
                    "text": {"type": "string", "description": "The text to type into the field."}
                },
                "required": ["selector", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_read",
            "description": "Read the visible text of the current page, or of a specific element if a selector is given. Read-only, no confirmation needed.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": ["string", "null"], "description": "Optional CSS selector. Omit or pass null to read the whole page."}},
                "required": []
            }
        }
    }
]

# Single source of truth the agent loop imports from.
ALL_TOOLS = FILE_TOOLS + SHELL_TOOLS + BROWSER_TOOLS
