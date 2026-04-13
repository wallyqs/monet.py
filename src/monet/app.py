"""Textual application entry point for monet."""

from __future__ import annotations

import json
import re
import subprocess
import sys

from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text

from monet.backends.base import ContentBlock
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, OptionList, RichLog, Rule, Static
from textual.widgets.option_list import Option

from textual.selection import Selection
from textual.strip import Strip
from textual.timer import Timer

from monet.backends import Backend, DSPyBackend, Message
from monet.commands import registry as command_registry
from monet.commands._builtins import register_builtins
from monet.providers import (
    AVAILABLE_PROVIDERS,
    DEFAULT_PROVIDER,
    Provider,
    provider_by_name,
)
from monet.tools import TOOLS

BANNER = """\
▗▖  ▗▖ ▗▄▖ ▗▖  ▗▖▗▄▄▄▖▗▄▄▄  ▗▄▄▖▗▖  ▗▖  
▐▛▚▞▜▌▐▌ ▐▌▐▛▚▖▐▌▐▌     █   ▐▌ ▐▌▝▚▞▘ 
▐▌  ▐▌▐▌ ▐▌▐▌ ▝▜▌▐▛▀▀▘  █   ▐▛▀▘  ▐▌  
▐▌  ▐▌▝▚▄▞▘▐▌  ▐▌▐▙▄▄▖  █ ▐▌▐▌    ▐▌     
"""


class MonetApp(App):
    """Main Textual app for monet."""

    TITLE = "monet"
    COMMAND_PALETTE_BINDING = ""

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+z", "suspend_process", "Suspend"),
        Binding("ctrl+o", "toggle_thinking", "Toggle thinking", show=False),
        Binding("escape", "cancel_chat", "Cancel", show=False),
        Binding("tab", "autocomplete", "Autocomplete", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        register_builtins()
        command_registry.load_all_plugins()
        self.backend: Backend = DSPyBackend(tools=TOOLS)
        self.history: list[Message] = []
        self.current_provider: Provider = DEFAULT_PROVIDER
        self.model = DEFAULT_PROVIDER.api_model
        self._apply_provider(DEFAULT_PROVIDER)
        self._spinner_timer: Timer | None = None
        self._spinner_index: int = 0
        self.show_thinking: bool = False

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #content-pane {
        height: 1fr;
        width: 1fr;
        background: $surface;
    }

    #banner {
        height: auto;
        width: auto;
        padding: 1 2 0 2;
        color: #F4A300;
        text-style: bold;
    }

    #banner.hidden {
        display: none;
    }

    #content {
        height: 1fr;
        width: 1fr;
        padding: 1 2;
        background: $surface;
    }

    Rule {
        margin: 0;
        color: $panel-lighten-2;
    }

    #status-bar {
        height: auto;
        width: 1fr;
        background: $surface;
    }

    #status {
        width: 1fr;
        height: auto;
        padding: 0 2;
        color: $text-muted;
    }

    #model-label {
        width: auto;
        padding: 0 2;
        color: $text-muted;
        text-align: right;
    }
    """

    def compose(self) -> ComposeResult:
        # Banner + Content
        with Vertical(id="content-pane"):
            yield Static(BANNER, id="banner")
            yield ContentLog(id="content", wrap=True, markup=True, highlight=True)

        #
        # Input Area
        # ────────
        # ❯
        # ────────
        #
        yield Rule(line_style="heavy")
        yield PromptBar()
        yield Rule(line_style="heavy")
        yield CommandSelector(id="command-selector")
        yield ModelSelector(id="model-selector")

        # Status bar below input area
        with Horizontal(id="status-bar"):
            yield Static("  [b]?[/b] for shortcuts", id="status")
            yield Static(f"[dim]{DEFAULT_PROVIDER.model}[/dim]", id="model-label")

    def on_mount(self) -> None:
        log = self.query_one("#content", ContentLog)
        log.write("[dim]Simple DSPy based coding harness[/dim]")
        log.write("")
        self._intro_line_count = 2
        self.query_one("#prompt-input", Input).focus()

        # action_suspend_process does not refresh the screen after the driver
        # re-enters application mode on SIGCONT, so we force a full repaint
        # ourselves when the resume signal fires.
        self.app_resume_signal.subscribe(self, self._on_resume)

    def predict(self, signature: str, **kwargs: object) -> dict[str, str]:
        """Run a dspy.Predict call using the current model.

        Convenience method for command plugins.

        Args:
            signature: DSPy signature string, e.g. "question -> answer".
            **kwargs: Input fields matching the signature.

        Returns:
            Dict mapping output field names to their string values.
            On error, returns {"error": "message"}.
        """
        return self.backend.predict(signature, self.model, **kwargs)

    def action_autocomplete(self) -> None:
        """Tab: autocomplete command from the selector, or do nothing."""
        inp = self.query_one("#prompt-input", MonetInput)
        if not inp.value.startswith("/"):
            return
        try:
            cmd_sel = self.query_one("#command-selector", CommandSelector)
            if cmd_sel.display and cmd_sel.option_count > 0:
                option = cmd_sel.get_option_at_index(cmd_sel.highlighted)
                cmd_name = str(option.id)
                inp.value = cmd_name + " "
                inp.cursor_position = len(inp.value)
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:
        """Keep focus on the input whenever a printable key is pressed."""
        inp = self.query_one("#prompt-input", MonetInput)
        if self.focused is not inp and event.is_printable:
            char = event.character or ""
            inp.focus()
            if char:
                self.call_after_refresh(inp.insert_text_at_cursor, char)

    def _check_banner(self) -> None:
        """Hide the banner and intro lines once the content log needs scrolling."""
        banner = self.query_one("#banner", Static)
        if banner.has_class("hidden"):
            return
        log = self.query_one("#content", ContentLog)
        if log.virtual_size.height > log.size.height:
            banner.add_class("hidden")
            # Permanently remove intro lines from the record
            n = getattr(self, "_intro_line_count", 0)
            if n and len(log._line_records) >= n:
                log._line_records = log._line_records[n:]
                log._rebuild_lines()

    def action_toggle_thinking(self) -> None:
        """Toggle display of thinking blocks — retroactively hides or shows all."""
        self.show_thinking = not self.show_thinking
        log = self.query_one("#content", ContentLog)
        log.set_tag_visible("thinking", self.show_thinking)
        state = "on" if self.show_thinking else "off"
        status = self.query_one("#status", Static)
        status.update(f"  [dim]thinking: {state}[/dim]")

    def _on_resume(self, _app: App) -> None:
        self.refresh(layout=True)
        self.screen.refresh(layout=True)

    def copy_to_clipboard(self, text: str) -> None:
        """Copy text to system clipboard, using pbcopy on macOS."""
        super().copy_to_clipboard(text)
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False)

    def on_text_selected(self) -> None:
        """Auto-copy to clipboard when a text selection is completed."""
        selected = self.screen.get_selected_text()
        if selected:
            self.copy_to_clipboard(selected)

    def _apply_provider(self, provider: Provider) -> None:
        """Switch the active model/provider and reconfigure the backend."""
        self.current_provider = provider
        self.model = provider.api_model
        if hasattr(self.backend, "configure"):
            self.backend.configure(  # type: ignore[attr-defined]
                api_base=provider.api_base,
                api_key=provider.resolve_api_key(),
            )
        try:
            self.query_one("#model-label", Static).update(
                f"[dim]{provider.model}[/dim]"
            )
        except Exception:
            pass  # widget not yet mounted during __init__

    def _open_model_selector(self) -> None:
        """Populate and show the model picker below the input area."""
        selector = self.query_one("#model-selector", ModelSelector)
        selector.clear_options()
        max_name = max(len(p.model) for p in AVAILABLE_PROVIDERS)
        current_idx = 0
        for i, p in enumerate(AVAILABLE_PROVIDERS):
            marker = "▸" if p.model == self.current_provider.model else " "
            label = Text.from_markup(
                f"{marker} [#F4A300]{p.model.ljust(max_name)}[/#F4A300]  [dim]{p.label}[/dim]"
            )
            selector.add_option(Option(label, id=p.model))
            if p.model == self.current_provider.model:
                current_idx = i
        selector.highlighted = current_idx
        selector.display = True
        selector.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection from command or model picker."""
        widget = event.option_list

        if isinstance(widget, CommandSelector):
            widget.display = False
            inp = self.query_one("#prompt-input", MonetInput)
            cmd = str(event.option_id)
            inp.value = ""
            inp.focus()
            log = self.query_one("#content", ContentLog)
            log.write("")
            log.write(f"[dim]❯[/dim] {escape(cmd)}")
            self._dispatch_command(cmd)
            return

        if isinstance(widget, ModelSelector):
            widget.display = False
            name = str(event.option_id)
            provider = provider_by_name(name)
            if provider is not None:
                self._apply_provider(provider)
                log = self.query_one("#content", ContentLog)
                log.write(
                    f"[#8AB060]switched to[/#8AB060] [b]{escape(provider.model)}[/b] [dim]({provider.label})[/dim]"
                )
            self.query_one("#prompt-input").focus()

    def _dispatch_command(self, value: str) -> None:
        """Route a slash command via the registry."""
        cmd_sel = self.query_one("#command-selector", CommandSelector)
        cmd_sel.display = False

        cmd = command_registry.get(value.split(maxsplit=1)[0])
        if cmd is None:
            log = self.query_one("#content", ContentLog)
            log.write(f"[#E05A3A]unknown command:[/#E05A3A] {escape(value)}")
            return
        self._run_command(value)

    @work(thread=True, exclusive=True, group="chat")
    def _run_command(self, value: str) -> None:
        """Execute a slash command on a background thread with spinner."""
        log = self.query_one("#content", ContentLog)
        self.call_from_thread(self._start_spinner)

        # Snapshot line count before the command writes its output
        lines_before = len(log.lines)
        try:
            command_registry.dispatch(self, value)
        except Exception as err:
            self.call_from_thread(
                log.write, f"[#E05A3A]command error:[/#E05A3A] {escape(str(err))}"
            )
        finally:
            self.call_from_thread(self._stop_spinner)

        # Capture whatever the command wrote to the log and add to chat
        # history so the LLM can reference it in follow-up conversation.
        output_lines = [s.text for s in log.lines[lines_before:]]
        if output_lines:
            output = "\n".join(output_lines).strip()
            self.history.append(Message(role="user", content=value))
            self.history.append(Message(role="assistant", content=output))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            return

        # Dismiss command selector if open
        cmd_sel = self.query_one("#command-selector", CommandSelector)
        cmd_sel.display = False

        log = self.query_one("#content", ContentLog)
        log.write("")
        log.write(f"[dim]❯[/dim] {escape(value)}")
        inp = self.query_one("#prompt-input", MonetInput)
        event.input.clear()

        if value.startswith("/"):
            self._dispatch_command(value)
            return

        inp.history_push(value)
        self._run_chat(value)

    def _start_spinner(self) -> None:
        self._spinner_index = 0
        self._tick_spinner()
        self._spinner_timer = self.set_interval(0.08, self._tick_spinner)

    def _tick_spinner(self) -> None:
        frame = SPINNER_FRAMES[self._spinner_index % len(SPINNER_FRAMES)]
        status = self.query_one("#status", Static)
        status.update(f"  {frame} [dim]working…[/dim]")
        self._spinner_index += 1

    def _stop_spinner(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self.query_one("#status", Static).update("")

    def action_cancel_chat(self) -> None:
        """Cancel any in-flight chat worker."""
        workers = self.workers._workers  # access the worker set
        cancelled = False
        for worker in list(workers):
            if worker.group == "chat" and worker.is_running:
                worker.cancel()
                cancelled = True
        if cancelled:
            self._stop_spinner()
            log = self.query_one("#content", ContentLog)
            log.write("[dim]  ⏺ cancelled[/dim]")

    # Runs on a background thread so the network call to the backend does not
    # block the Textual event loop. All UI mutations from inside must go
    # through ``call_from_thread``.
    @work(thread=True, exclusive=True, group="chat")
    def _run_chat(self, value: str) -> None:
        log = self.query_one("#content", ContentLog)

        self.call_from_thread(self._start_spinner)

        def status_fn(line: str) -> None:
            pass  # spinner handles the status bar while working

        result = self.backend.chat(value, self.model, self.history, status_fn)
        self.call_from_thread(self._stop_spinner)

        if result.err is not None:
            err_text = escape(str(result.err))
            self.call_from_thread(log.write, f"[#E05A3A]error:[/#E05A3A] {err_text}")
            return

        reply = result.reply or result.content

        # Render trajectory blocks (thinking, tool calls, tool results)
        # before the final reply text.
        for block in result.blocks:
            if block.type == "text":
                continue  # final reply rendered separately below
            self.call_from_thread(self._write_block, log, block)

        width = log.scrollable_content_region.width or 80
        self.call_from_thread(log.write, f"[#F4A300]{'─' * width}[/#F4A300]")
        self.call_from_thread(self.write_markdown, reply)
        self.history.append(Message(role="user", content=value))
        self.history.append(Message(role="assistant", content=reply))

    def _write_block(self, log: "ContentLog", block: ContentBlock) -> None:
        """Render a single trajectory content block."""
        if block.type == "thinking":
            log.begin_thinking()
            log.write("[#D48B00]  ⏺ thinking[/#D48B00]")
            for line in block.thinking.strip().splitlines():
                log.write(f"[dim]    {escape(line)}[/dim]")
            log.end_thinking()
            if not self.show_thinking:
                log.set_tag_visible("thinking", False)
        elif block.type == "toolCall":
            args = json.dumps(block.arguments) if block.arguments else ""
            log.write(
                f"[#FFB833]  ⏺ {escape(block.tool_name)}[/#FFB833]"
                f" [dim]{escape(args)}[/dim]"
            )
        elif block.type == "toolResult":
            prefix = "[#E05A3A]  ⎿[/#E05A3A]" if block.is_error else "[dim]  ⎿[/dim]"
            content = block.content.strip()
            # Render unified diffs with syntax highlighting
            if content.startswith("--- ") or content.startswith("edited "):
                diff_start = content.find("--- ")
                if diff_start >= 0:
                    preamble = content[:diff_start].strip()
                    diff_text = content[diff_start:]
                    if preamble:
                        log.write(f"{prefix} [dim]{escape(preamble)}[/dim]")
                    log.write(f"{prefix}")
                    log.write(Syntax(diff_text, "diff", theme="monokai", padding=0))
                    return
            for line in content.splitlines():
                log.write(f"{prefix} [dim]{escape(line)}[/dim]")

    # Regex to match fenced code blocks: ```lang\n...\n```
    _CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

    def write_markdown(self, text: str) -> None:
        """Write markdown to the content log.

        Fenced code blocks are rendered via ``rich.syntax.Syntax`` (no
        padding) so they produce simple strips compatible with text
        selection. Everything else is written as Rich-markup escaped text
        with lightweight inline styling.
        """
        log = self.query_one("#content", ContentLog)
        pos = 0
        for m in self._CODE_BLOCK_RE.finditer(text):
            # Write the prose before this code block
            before = text[pos : m.start()].strip()
            if before:
                self._write_prose(log, before)
            lang = m.group(1) or "text"
            code = m.group(2).rstrip("\n")
            log.write(Syntax(code, lang, theme="monokai", word_wrap=True, padding=0))
            pos = m.end()
        # Write any remaining prose after the last code block
        after = text[pos:].strip()
        if after:
            self._write_prose(log, after)

    @staticmethod
    def _write_prose(log: "ContentLog", prose: str) -> None:
        """Write non-code prose with basic inline markdown styling."""
        lines = prose.split("\n")
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                log.write("")
                continue
            # Headings
            if line.startswith("#"):
                heading = line.lstrip("# ").strip()
                log.write(Text(heading, style="bold"))
                continue
            # Escape Rich markup brackets first, then apply our styling
            safe = escape(stripped_line)
            # Bold: **text**
            safe = re.sub(r"\*\*(.+?)\*\*", r"[b]\1[/b]", safe)
            # Inline code: `text`
            safe = re.sub(r"`(.+?)`", r"[bold #FFB833]\1[/bold #FFB833]", safe)
            # List items: - or *
            if safe.startswith("- ") or safe.startswith("* "):
                safe = "  " + safe
            log.write(safe)


class PromptBar(Horizontal):
    """Prompt marker (``❯``) sitting next to the input field."""

    DEFAULT_CSS = """
    PromptBar {
        height: 1;
        width: 1fr;
    }
    PromptBar > #prompt-marker {
        width: 3;
        content-align: center middle;
        color: #F4A300;
    }
    PromptBar > Input {
        border: none;
        padding: 0;
        height: 1;
        width: 1fr;
        background: $surface;
    }
    PromptBar > Input:focus {
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("❯", id="prompt-marker")
        yield MonetInput(placeholder="Input goes here", id="prompt-input")


SPINNER_FRAMES = ("⠄", "⠆", "⠇", "⠋", "⠙", "⠸", "⠰", "⠠", "⠰", "⠸", "⠙", "⠋", "⠇", "⠆")


class MonetInput(Input):
    """Input with Emacs-style readline bindings.

    Overrides the default ``ctrl+f`` (which Textual binds to
    ``delete_right_word``) to move the cursor forward one char, and adds a
    kill/yank pair: ``ctrl+k`` kills from the cursor to end-of-line *into an
    instance-local buffer*, and ``ctrl+y`` yanks that buffer back at the
    cursor. This is separate from the system clipboard so it survives across
    any intervening copy/paste.
    """

    BINDINGS = [
        Binding("ctrl+b", "cursor_left", "Back char", show=False),
        Binding("ctrl+f", "cursor_right", "Forward char", show=False),
        Binding("ctrl+p", "history_prev", "History prev", show=False),
        Binding("ctrl+n", "history_next", "History next", show=False),
        Binding("ctrl+k", "kill_to_end", "Kill to end", show=False),
        Binding("ctrl+y", "yank", "Yank", show=False),
    ]

    def _on_key(self, event: "events.Key") -> None:
        if event.character == "?" and not self.value:
            event.prevent_default()
            event.stop()
            try:
                status = self.app.query_one("#status", Static)
                status.update(
                    "  [dim]/ for commands   ctrl + o toggle thinking[/dim]\n"
                    "  [dim]esc to cancel    ctrl + z to suspend[/dim]"
                )
            except Exception:
                pass
            return

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._kill_buffer: str = ""
        self._input_history: list[str] = []
        self._history_index: int = -1  # -1 = not navigating
        self._history_stash: str = ""  # saves in-progress input

    def history_push(self, value: str) -> None:
        """Record a submitted input in history."""
        if value and (not self._input_history or self._input_history[-1] != value):
            self._input_history.append(value)
        self._history_index = -1

    def action_history_prev(self) -> None:
        """Navigate to previous history entry, or focus command selector if visible."""
        try:
            cmd_sel = self.app.query_one("#command-selector", CommandSelector)
            if cmd_sel.display:
                cmd_sel.focus()
                return
        except Exception:
            pass
        if not self._input_history:
            return
        if self._history_index == -1:
            self._history_stash = self.value
            self._history_index = len(self._input_history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return
        self.value = self._input_history[self._history_index]
        self.cursor_position = len(self.value)

    def action_history_next(self) -> None:
        """Navigate to next history entry, or focus command selector if visible."""
        try:
            cmd_sel = self.app.query_one("#command-selector", CommandSelector)
            if cmd_sel.display:
                cmd_sel.focus()
                return
        except Exception:
            pass
        if self._history_index == -1:
            return
        if self._history_index < len(self._input_history) - 1:
            self._history_index += 1
            self.value = self._input_history[self._history_index]
        else:
            self._history_index = -1
            self.value = self._history_stash
        self.cursor_position = len(self.value)

    def watch_value(self, value: str) -> None:
        try:
            status = self.app.query_one("#status", Static)
            if value:
                status.update("")
            else:
                status.update("  [b]?[/b] for shortcuts")
        except Exception:
            pass
        try:
            cmd_sel = self.app.query_one("#command-selector", CommandSelector)
            if value.startswith("/"):
                prefix = value.lower()
                commands = command_registry.list_commands()
                cmd_sel.clear_options()
                if commands:
                    max_name = max(len(c) for c, _ in commands)
                    for cmd, desc in commands:
                        if cmd.startswith(prefix) or prefix == "/":
                            label = Text.from_markup(
                                f"  [#F4A300]{cmd.ljust(max_name)}[/#F4A300]  [dim]{desc}[/dim]"
                            )
                            cmd_sel.add_option(Option(label, id=cmd))
                if cmd_sel.option_count > 0:
                    cmd_sel.highlighted = 0
                    cmd_sel.display = True
                else:
                    cmd_sel.display = False
            else:
                cmd_sel.display = False
        except Exception:
            pass

    def action_kill_to_end(self) -> None:
        pos = self.cursor_position
        killed = self.value[pos:]
        if killed:
            self._kill_buffer = killed
        self.value = self.value[:pos]

    def action_yank(self) -> None:
        if not self._kill_buffer:
            return
        pos = self.cursor_position
        self.value = self.value[:pos] + self._kill_buffer + self.value[pos:]
        self.cursor_position = pos + len(self._kill_buffer)


class ContentLog(RichLog, can_focus=False):
    """RichLog that supports mouse text selection.

    ``RichLog`` stores rendered lines as ``Strip`` objects but does not
    implement the three hooks the framework needs for selection:

    1. ``apply_offsets`` in ``_render_line`` — embeds positional metadata so
       the Screen can map mouse coordinates to text positions.
    2. ``get_selection`` — returns the plain-text under a Selection range.
    3. ``selection_updated`` — invalidates the line cache and refreshes so
       the selection highlight repaints.

    We also apply the ``screen--selection`` style to the affected segments
    so the user can see what's selected.
    """

    ALLOW_SELECT = True

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # Parallel record of every line: (strip, tag).
        # tag is "" for normal, "thinking" for thinking, "intro" for intro.
        self._line_records: list[tuple["Strip", str]] = []
        self._write_tag: str = ""
        self._hidden_tags: set[str] = set()

    def begin_thinking(self) -> None:
        self._write_tag = "thinking"

    def end_thinking(self) -> None:
        self._write_tag = ""

    def write(self, *args: object, **kwargs: object) -> "ContentLog":  # type: ignore[override]
        before = len(self.lines)
        result = super().write(*args, **kwargs)  # type: ignore[arg-type]
        for i in range(before, len(self.lines)):
            self._line_records.append((self.lines[i], self._write_tag))
        try:
            self.app._check_banner()  # type: ignore[attr-defined]
        except Exception:
            pass
        return result

    def set_tag_visible(self, tag: str, visible: bool) -> None:
        """Show or hide all lines with the given tag and rebuild the display."""

        if visible:
            self._hidden_tags.discard(tag)
        else:
            self._hidden_tags.add(tag)
        self._rebuild_lines()

    def _rebuild_lines(self) -> None:
        from textual.geometry import Size

        self.lines[:] = [
            strip for strip, tag in self._line_records if tag not in self._hidden_tags
        ]
        self._line_cache.clear()
        self.virtual_size = Size(self._widest_line_width, len(self.lines))
        self.scroll_end(animate=False)
        self.refresh()

    def _render_line(self, y: int, scroll_x: int, width: int) -> Strip:
        if y >= len(self.lines):
            return Strip.blank(width, self.rich_style)

        selection = self.text_selection
        key = (y + self._start_line, scroll_x, width, self._widest_line_width)
        if key in self._line_cache and selection is None:
            return self._line_cache[key]

        line = self.lines[y]

        # Apply selection highlighting before cropping to viewport.
        if selection is not None:
            span = selection.get_span(y)
            if span is not None:
                start, end = span
                if end == -1:
                    end = line.cell_length
                sel_style = self.screen.get_component_rich_style("screen--selection")
                before = line.crop(0, start)
                selected = line.crop(start, end).apply_style(sel_style)
                after = line.crop(end, line.cell_length)
                segments = (
                    list(before._segments)
                    + list(selected._segments)
                    + list(after._segments)
                )
                line = Strip(segments, line.cell_length)

        line = line.crop_extend(scroll_x, scroll_x + width, self.rich_style)
        line = line.apply_offsets(scroll_x, y)

        if selection is None:
            self._line_cache[key] = line
        return line

    def get_selection(self, selection: "Selection") -> tuple[str, str] | None:

        text = "\n".join(strip.text for strip in self.lines)
        return selection.extract(text), "\n"

    def selection_updated(self, selection: "Selection | None") -> None:
        self._line_cache.clear()
        self.refresh()


class CommandSelector(OptionList):
    """Slash-command picker, shown below the input when the user types ``/``."""

    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss", show=False),
        Binding("ctrl+p", "cursor_up", "Up", show=False),
        Binding("ctrl+n", "cursor_down", "Down", show=False),
    ]

    DEFAULT_CSS = """
    CommandSelector {
        display: none;
        height: auto;
        max-height: 8;
        background: $surface;
        padding: 0 2;
        border: none;
        & > .option-list--option {
            background: $surface;
            padding: 0;
        }
        & > .option-list--option-highlighted,
        &:focus > .option-list--option-highlighted {
            color: #FFB833;
            background: $surface;
            text-style: bold;
        }
        & > .option-list--option-hover {
            background: $surface;
        }
    }
    """

    def action_dismiss(self) -> None:
        self.display = False
        self.app.query_one("#prompt-input").focus()


class ModelSelector(OptionList):
    """Keyboard-navigable model picker, shown below the input area."""

    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss", show=False),
        Binding("ctrl+p", "cursor_up", "Up", show=False),
        Binding("ctrl+n", "cursor_down", "Down", show=False),
    ]

    DEFAULT_CSS = """
    ModelSelector {
        display: none;
        height: auto;
        max-height: 14;
        background: $surface;
        padding: 0 2;
        border: none;
        & > .option-list--option {
            background: $surface;
            padding: 0;
        }
        & > .option-list--option-highlighted,
        &:focus > .option-list--option-highlighted {
            color: #FFB833;
            background: $surface;
            text-style: bold;
        }
        & > .option-list--option-hover {
            background: $surface;
        }
    }
    """

    def action_dismiss(self) -> None:
        self.display = False
        self.app.query_one("#prompt-input").focus()


def main() -> None:
    """Launch the monet TUI."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("-v", "--version"):
        from monet import __version__

        print(f"monet {__version__}")
        return

    from pathlib import Path

    # Source .env via shell to handle 'export' syntax correctly.
    env_file = Path(".env")
    if env_file.is_file():
        import os
        import shlex

        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip leading 'export '
            if line.startswith("export "):
                line = line[7:]
            key, _, value = line.partition("=")
            if key:
                os.environ.setdefault(key.strip(), value.strip())

    MonetApp().run()


if __name__ == "__main__":
    main()
