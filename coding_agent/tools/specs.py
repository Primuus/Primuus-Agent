"""The three first-stage tool definitions."""

TOOL_SPECS = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 file in the workspace",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": "Write a UTF-8 file in the workspace",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_shell",
        "description": "Run a shell command in the workspace",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
]

REPOSITORY_TOOL_SPECS = TOOL_SPECS + [
    {
        "name": "list_files",
        "description": "List repository files, including untracked files, up to 300 paths",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "search_text",
        "description": "Search repository files for literal text and show matching file and line",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file_range",
        "description": "Read inclusive line range from a UTF-8 file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path", "start_line", "end_line"],
            "additionalProperties": False,
        },
    },
    {
        "name": "edit_file",
        "description": "Replace one exact text span in a UTF-8 file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "git_status",
        "description": "Show the repository's short Git status",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "git_diff",
        "description": "Show tracked changes relative to the session's base commit",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
]

REPOSITORY_TOOL_SPECS.append({
    "name": "update_plan",
    "description": "Set or update a short milestone plan for a multi-step task",
    "parameters": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                    },
                    "required": ["description", "status"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    },
})
