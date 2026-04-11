"""Coding tools for the ReAct agent — read, write, edit, bash, grep, list_dir."""

import difflib
import os
import re
import subprocess


def read(file_path: str, offset: int = 0, limit: int = 0) -> str:
    """Read a file and return its contents with line numbers.

    Args:
        file_path: Absolute or relative path to the file.
        offset: Line number to start reading from (0-based, default 0).
        limit: Maximum number of lines to return (0 = all).
    """
    if not file_path:
        return "error: file_path is required"
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return f"error: file not found: {file_path}"
    except PermissionError:
        return f"error: permission denied: {file_path}"

    if offset > 0:
        lines = lines[offset:]
    if limit > 0:
        lines = lines[:limit]

    numbered = []
    start = offset + 1
    for i, line in enumerate(lines, start=start):
        numbered.append(f"{i}\t{line.rstrip()}")
    return "\n".join(numbered)


def write(file_path: str, content: str) -> str:
    """Write content to a file, creating directories if needed. Overwrites any existing file.

    Args:
        file_path: Absolute or relative path to the file.
        content: The full content to write.
    """
    if not file_path:
        return "error: file_path is required"
    try:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"wrote {file_path}"
    except PermissionError:
        return f"error: permission denied: {file_path}"


def edit(file_path: str, old_string: str, new_string: str) -> str:
    """Replace an exact string in a file. The old_string must appear exactly once.

    Args:
        file_path: Path to the file to modify.
        old_string: The exact text to find (must be unique in the file).
        new_string: The replacement text.
    """
    if not file_path:
        return "error: file_path is required"
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"error: file not found: {file_path}"

    count = content.count(old_string)
    if count == 0:
        return "error: old_string not found in file"
    if count > 1:
        return f"error: old_string found at {count} locations (must be unique)"

    new_content = content.replace(old_string, new_string, 1)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    diff = _unified_diff(content, new_content, file_path)
    return f"edited {file_path}\n{diff}"


def _unified_diff(old: str, new: str, path: str) -> str:
    """Generate a compact unified diff between two strings."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=path, tofile=path, n=3)
    return "".join(diff).rstrip()


def bash(command: str, timeout: int = 30) -> str:
    """Run a shell command and return its combined stdout and stderr.

    Args:
        command: The shell command to execute.
        timeout: Maximum seconds to wait (default 30).
    """
    if not command:
        return "error: command is required"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            output += f"\nexit code: {result.returncode}"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {timeout}s"


def grep(pattern: str, path: str = ".") -> str:
    """Search for a regex pattern in files under the given path.

    Args:
        pattern: Regular expression pattern to search for.
        path: File or directory to search in (default: current directory).
    """
    if not pattern:
        return "error: pattern is required"

    matches: list[str] = []

    if os.path.isfile(path):
        _grep_file(path, pattern, matches)
    elif os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                _grep_file(fpath, pattern, matches)
    else:
        return f"error: path not found: {path}"

    if not matches:
        return "no matches found"
    return "\n".join(matches)


def _grep_file(fpath: str, pattern: str, matches: list[str]) -> None:
    try:
        with open(fpath, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                if re.search(pattern, line):
                    matches.append(f"{fpath}:{lineno}:{line.rstrip()}")
    except (PermissionError, OSError):
        pass


def list_dir(path: str = ".") -> str:
    """List files and directories at the given path. Directories have a trailing '/'.

    Args:
        path: Directory to list (default: current directory).
    """
    if not path:
        return "error: path is required"
    if not os.path.isdir(path):
        return f"error: not a directory: {path}"

    entries: list[str] = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full):
                entries.append(f"{name}/")
            else:
                entries.append(name)
    except PermissionError:
        return f"error: permission denied: {path}"

    return "\n".join(entries) if entries else "(empty directory)"


def register_command(file_path: str) -> str:
    """Load or reload a slash command plugin from a Python file.

    The file must export NAME (str), DESCRIPTION (str), and handler(app, args).
    Use this after writing a new command file to .monet/commands/ to make it
    available immediately. Creates .monet/commands/ if it does not exist.

    Args:
        file_path: Path to the .py plugin file.
    """
    if not file_path:
        return "error: file_path is required"
    from monet.commands import USER_COMMANDS_DIR, registry

    USER_COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    err = registry.load_plugin(file_path)
    if err:
        return f"error: {err}"
    return f"registered command from {file_path}"


TOOLS = [read, write, edit, bash, grep, list_dir, register_command]
