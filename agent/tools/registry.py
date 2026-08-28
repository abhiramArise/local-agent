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

# Single source of truth the agent loop imports from.
ALL_TOOLS = FILE_TOOLS
