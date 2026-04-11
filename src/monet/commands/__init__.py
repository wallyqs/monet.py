"""Dynamic command registry with plugin loading."""

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

HandlerFunc = Callable[..., None]  # handler(app, args: str) -> None

USER_COMMANDS_DIR = Path(".monet") / "commands"


@dataclass
class Command:
    """A registered slash command."""

    name: str
    description: str
    handler: HandlerFunc
    source: str = ""


class CommandRegistry:
    """In-memory registry of slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(
        self, name: str, description: str, handler: HandlerFunc, source: str = ""
    ) -> None:
        if not name.startswith("/"):
            name = "/" + name
        self._commands[name] = Command(
            name=name, description=description, handler=handler, source=source
        )

    def unregister(self, name: str) -> bool:
        if not name.startswith("/"):
            name = "/" + name
        return self._commands.pop(name, None) is not None

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def list_commands(self) -> list[tuple[str, str]]:
        return [(c.name, c.description) for c in self._commands.values()]

    def dispatch(self, app: Any, value: str) -> bool:
        """Parse input, find the command, call its handler.

        Returns True if a command was found and dispatched.
        """
        parts = value.split(maxsplit=1)
        cmd_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        cmd = self._commands.get(cmd_name)
        if cmd is None:
            return False
        cmd.handler(app, args)
        return True

    def load_plugin(self, file_path: str | Path) -> str | None:
        """Load or reload a plugin file. Returns error string or None on success."""
        file_path = Path(file_path)
        if not file_path.exists():
            return f"file not found: {file_path}"

        # Use resolved path hash to avoid module name collisions across directories
        path_id = file_path.resolve().as_posix().replace("/", "_").replace(".", "_")
        module_name = f"monet.commands._plugin_{path_id}"

        # Remove old module to force a fresh load (handles reload case)
        sys.modules.pop(module_name, None)

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return f"cannot load: {file_path}"
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            # Read and compile source directly to bypass bytecode cache (.pyc),
            # which can serve stale code when file size and mtime are unchanged.
            source = file_path.read_bytes()
            code = compile(source, str(file_path), "exec")
            exec(code, module.__dict__)
        except Exception as e:
            del sys.modules[module_name]
            return f"import error: {e}"

        name = getattr(module, "NAME", None)
        desc = getattr(module, "DESCRIPTION", None)
        handler = getattr(module, "handler", None)
        if not name or not desc or not callable(handler):
            return (
                f"invalid plugin {file_path.name}: "
                "must export NAME, DESCRIPTION, and handler()"
            )

        self.register(name, desc, handler, source=str(file_path))
        return None

    def load_all_plugins(self) -> list[str]:
        """Scan ~/.monet/commands/ for plugin files and load them.

        Returns list of error messages (empty = all ok).
        """
        errors: list[str] = []
        if not USER_COMMANDS_DIR.is_dir():
            return errors
        for f in sorted(USER_COMMANDS_DIR.glob("*.py")):
            if f.name.startswith("_"):
                continue
            err = self.load_plugin(f)
            if err:
                errors.append(err)
        return errors


registry = CommandRegistry()
