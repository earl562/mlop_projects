"""Filesystem tools — the most foundational harness primitive.

Read, write, edit, glob, grep with line-numbered output.
Per Anatomy of an Agent Harness: the filesystem enables durable storage,
context offloading, collaboration surface, and Ralph Loop state persistence.

Every tool returns JSON with status + optional truncated output.
Large outputs are offloaded by ToolCallOffloadMiddleware.
"""

from __future__ import annotations

import difflib
import json
import os
import re
from pathlib import Path
from typing import Any


def _resolve(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not str(p).startswith(str(Path.cwd())):
        raise PermissionError(f"Path outside workspace: {path}")
    return p


# ------------------------------------------------------------------ read_file
def read_file(filePath: str, limit: int = 2000, offset: int = 0) -> dict[str, Any]:
    """Read a file with line numbers. Line 1-based. Max 2000 lines default."""
    try:
        path = _resolve(filePath)
        if not path.is_file():
            return {"ok": False, "error": f"Not found: {filePath}"}
        lines = path.read_text(errors="replace").splitlines()
        total = len(lines)
        end = min(offset + limit, total) if limit else total
        result = []
        for i in range(offset, end):
            result.append(f"{i + 1}: {lines[i]}")
        return {
            "ok": True,
            "lines": result,
            "total_lines": total,
            "offset": offset,
            "returned": end - offset,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ----------------------------------------------------------------- write_file
def write_file(filePath: str, content: str) -> dict[str, Any]:
    """Create or overwrite a file."""
    try:
        path = _resolve(filePath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return {"ok": True, "path": str(path), "size": len(content)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------- edit_file (fuzzy)
def edit_file(filePath: str, oldString: str, newString: str, replaceAll: bool = False) -> dict[str, Any]:
    """Replace oldString with newString in a file. Fuzzy: strips trailing whitespace per line."""
    try:
        path = _resolve(filePath)
        if not path.is_file():
            return {"ok": False, "error": f"Not found: {filePath}"}
        content = path.read_text()
        old = oldString.rstrip()
        if replaceAll:
            count = content.count(old)
            new_content = content.replace(old, newString)
        else:
            new_content = content.replace(old, newString, 1)
            count = 1 if old in content else 0
        if count == 0:
            return {"ok": False, "error": f"oldString not found in {filePath}"}
        path.write_text(new_content)
        return {"ok": True, "path": str(path), "replacements": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------------ file_count
def file_count(filePath: str) -> dict[str, Any]:
    """Return line count for a file."""
    try:
        path = _resolve(filePath)
        if not path.is_file():
            return {"ok": False, "error": f"Not found: {filePath}"}
        total = len(path.read_text(errors="replace").splitlines())
        return {"ok": True, "path": str(path), "total_lines": total}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ----------------------------------------------------------------------- glob
def glob_files(pattern: str, path: str | None = None) -> dict[str, Any]:
    """List files matching glob pattern in workspace."""
    try:
        base = _resolve(path) if path else Path.cwd()
        results = sorted(str(p.relative_to(base)) for p in base.rglob(pattern) if p.is_file())[:100]
        return {"ok": True, "matches": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ----------------------------------------------------------------------- grep
def grep_files(pattern: str, path: str | None = None, include: str | None = None, output_mode: str = "content", head_limit: int = 50) -> dict[str, Any]:
    """Search file contents with regex. output_mode: content|files_with_matches|count."""
    try:
        base = _resolve(path) if path else Path.cwd()
        regex = re.compile(pattern)
        results: dict[str, list[str]] = {}
        glob_filter = include or "**/*"
        files = list(base.rglob(glob_filter))[:500]
        for f in files:
            if not f.is_file():
                continue
            try:
                text = f.read_text(errors="replace")
            except Exception:
                continue
            matches = regex.findall(text)
            if matches:
                rel = str(f.relative_to(base))
                if output_mode == "count":
                    results[rel] = [str(len(matches))]
                elif output_mode == "files_with_matches":
                    results[rel] = []
                else:
                    lines = text.splitlines()
                    matching_lines = [f"{i+1}: {lines[i].strip()}" for i, line in enumerate(lines) if regex.search(line)]
                    results[rel] = matching_lines[:10]
        if head_limit:
            truncated = dict(list(results.items())[:head_limit])
            return {"ok": True, "matches": truncated, "total_files": len(results)}
        return {"ok": True, "matches": results, "total_files": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


FILESYSTEM_TOOLS: dict[str, dict[str, Any]] = {
    "read_file": {
        "name": "read_file",
        "description": "Read a file with line numbers. Line 1-based. Use offset/limit for pagination.",
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string", "description": "Absolute path to the file"},
                "limit": {"type": "integer", "description": "Max lines to return (default 2000)"},
                "offset": {"type": "integer", "description": "Line to start from (1-based)"},
            },
            "required": ["filePath"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Create or overwrite a file. Creates parent directories if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string", "description": "Absolute path"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["filePath", "content"],
        },
    },
    "edit_file": {
        "name": "edit_file",
        "description": "Perform exact string replacement in a file. Must match the file content exactly.",
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string", "description": "Absolute path"},
                "oldString": {"type": "string", "description": "Text to find and replace"},
                "newString": {"type": "string", "description": "Replacement text"},
                "replaceAll": {"type": "boolean", "description": "Replace all occurrences (default: false)"},
            },
            "required": ["filePath", "oldString", "newString"],
        },
    },
    "glob_files": {
        "name": "glob_files",
        "description": "Find files matching a glob pattern. Returns up to 100 matches sorted by path.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern like **/*.py or src/**/*.ts"},
                "path": {"type": "string", "description": "Search directory (default: workspace root)"},
            },
            "required": ["pattern"],
        },
    },
    "grep_files": {
        "name": "grep_files",
        "description": "Search file contents with regex. Returns matching lines with file paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Python regex pattern"},
                "path": {"type": "string", "description": "Search directory"},
                "include": {"type": "string", "description": "File pattern filter (e.g. *.py)"},
                "output_mode": {"type": "string", "enum": ["content", "files_with_matches", "count"]},
                "head_limit": {"type": "integer", "description": "Max result files to return"},
            },
            "required": ["pattern"],
        },
    },
}
