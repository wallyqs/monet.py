"""Headless TUI tests for MonetApp."""

import asyncio

import pytest

from monet.app import MonetApp, MonetInput, ContentLog, CommandSelector, ModelSelector
from monet.backends.base import ContentBlock
from monet.backends.dummy import DummyBackend
from monet.commands import registry


@pytest.fixture
def app():
    """Create a MonetApp with DummyBackend for deterministic tests."""
    a = MonetApp()
    a.backend = DummyBackend()
    a.model = "test"
    return a


# ── App startup ──────────────────────────────────────────────────────


class TestAppStartup:
    @pytest.mark.asyncio
    async def test_mounts(self, app):
        async with app.run_test(headless=True) as pilot:
            assert app.query_one("#content", ContentLog) is not None
            assert app.query_one("#prompt-input", MonetInput) is not None
            assert app.query_one("#status") is not None
            assert app.query_one("#model-label") is not None

    @pytest.mark.asyncio
    async def test_default_status(self, app):
        async with app.run_test(headless=True) as pilot:
            status = app.query_one("#status")
            text = status.render_line(0).text.strip()
            assert "? for shortcuts" in text

    @pytest.mark.asyncio
    async def test_banner_visible_initially(self, app):
        async with app.run_test(headless=True) as pilot:
            banner = app.query_one("#banner")
            assert not banner.has_class("hidden")


# ── Input behavior ───────────────────────────────────────────────────


class TestInput:
    @pytest.mark.asyncio
    async def test_question_mark_shows_help(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            await pilot.press("?")
            await pilot.pause()
            assert inp.value == ""
            status = app.query_one("#status")
            text = status.render_line(0).text.strip()
            assert "/ for commands" in text

    @pytest.mark.asyncio
    async def test_typing_clears_status(self, app):
        async with app.run_test(headless=True) as pilot:
            await pilot.press("h")
            await pilot.pause()
            status = app.query_one("#status")
            text = status.render_line(0).text.strip()
            assert text == ""

    @pytest.mark.asyncio
    async def test_clearing_restores_status(self, app):
        async with app.run_test(headless=True) as pilot:
            await pilot.press("h")
            await pilot.pause()
            await pilot.press("backspace")
            await pilot.pause()
            status = app.query_one("#status")
            text = status.render_line(0).text.strip()
            assert "? for shortcuts" in text

    @pytest.mark.asyncio
    async def test_auto_focus_on_typing(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            # Focus something else first
            log = app.query_one("#content")
            # ContentLog has can_focus=False, so focus the model selector instead
            # Just verify typing refocuses to input
            await pilot.press("a")
            await pilot.pause()
            assert app.focused is inp


# ── Kill / Yank ──────────────────────────────────────────────────────


class TestKillYank:
    @pytest.mark.asyncio
    async def test_kill_and_yank(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            inp.value = "hello world"
            inp.cursor_position = 6
            await pilot.press("ctrl+k")
            await pilot.pause()
            assert inp.value == "hello "
            assert inp._kill_buffer == "world"

            inp.cursor_position = 0
            await pilot.press("ctrl+y")
            await pilot.pause()
            assert inp.value == "worldhello "

    @pytest.mark.asyncio
    async def test_cursor_movement(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            inp.value = "abc"
            inp.cursor_position = 1
            await pilot.press("ctrl+f")
            await pilot.pause()
            assert inp.cursor_position == 2
            await pilot.press("ctrl+b")
            await pilot.pause()
            assert inp.cursor_position == 1


# ── Input history ────────────────────────────────────────────────────


class TestInputHistory:
    @pytest.mark.asyncio
    async def test_history_navigation(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            for text in ["aaa", "bbb", "ccc"]:
                for ch in text:
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause()

            assert inp._input_history == ["aaa", "bbb", "ccc"]

            await pilot.press("ctrl+p")
            await pilot.pause()
            assert inp.value == "ccc"

            await pilot.press("ctrl+p")
            await pilot.pause()
            assert inp.value == "bbb"

            await pilot.press("ctrl+n")
            await pilot.pause()
            assert inp.value == "ccc"

            await pilot.press("ctrl+n")
            await pilot.pause()
            assert inp.value == ""

    @pytest.mark.asyncio
    async def test_stash_preserves_draft(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            for ch in "aaa":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause()

            for ch in "draft":
                await pilot.press(ch)
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert inp.value == "aaa"

            await pilot.press("ctrl+n")
            await pilot.pause()
            assert inp.value == "draft"

    @pytest.mark.asyncio
    async def test_commands_not_in_history(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            inp.value = "/model"
            await pilot.press("enter")
            await pilot.pause()
            assert "/model" not in inp._input_history


# ── Command selector ─────────────────────────────────────────────────


class TestCommandSelector:
    @pytest.mark.asyncio
    async def test_slash_shows_selector(self, app):
        async with app.run_test(headless=True) as pilot:
            cmd_sel = app.query_one("#command-selector", CommandSelector)
            await pilot.press("/")
            await pilot.pause()
            assert cmd_sel.display is True
            assert cmd_sel.option_count > 0

    @pytest.mark.asyncio
    async def test_escape_dismisses(self, app):
        async with app.run_test(headless=True) as pilot:
            cmd_sel = app.query_one("#command-selector", CommandSelector)
            await pilot.press("/")
            await pilot.pause()
            await pilot.press("ctrl+n")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert cmd_sel.display is False

    @pytest.mark.asyncio
    async def test_no_match_hides(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            cmd_sel = app.query_one("#command-selector", CommandSelector)
            for ch in "/zzz":
                await pilot.press(ch)
                await pilot.pause()
            assert cmd_sel.display is False


# ── Model switching ──────────────────────────────────────────────────


class TestModelSwitching:
    @pytest.mark.asyncio
    async def test_model_command_opens_selector(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            inp.value = "/model"
            await pilot.press("enter")
            await pilot.pause()
            model_sel = app.query_one("#model-selector", ModelSelector)
            assert model_sel.display is True

    @pytest.mark.asyncio
    async def test_model_direct_switch(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            inp.value = "/model gpt-4o"
            await pilot.press("enter")
            await pilot.pause()
            assert app.current_provider.model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_model_label_updates(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            inp.value = "/model gpt-4o"
            await pilot.press("enter")
            await pilot.pause()
            label = app.query_one("#model-label")
            text = label.render_line(0).text.strip()
            assert "gpt-4o" in text

    @pytest.mark.asyncio
    async def test_unknown_model(self, app):
        async with app.run_test(headless=True) as pilot:
            inp = app.query_one("#prompt-input", MonetInput)
            inp.value = "/model nonexistent"
            await pilot.press("enter")
            await pilot.pause()
            log = app.query_one("#content", ContentLog)
            text = "\n".join(s.text for s in log.lines)
            assert "unknown model" in text


# ── Thinking toggle ──────────────────────────────────────────────────


class TestThinkingToggle:
    @pytest.mark.asyncio
    async def test_toggle_hides_and_shows(self, app):
        async with app.run_test(headless=True) as pilot:
            log = app.query_one("#content", ContentLog)
            log.clear()
            log._line_records.clear()
            await pilot.pause()

            app._write_block(
                log,
                ContentBlock(type="thinking", thinking="thought 1"),
            )
            log.write("visible line")
            await pilot.pause()

            text = "\n".join(s.text for s in log.lines)
            # Default: thinking hidden
            assert "thought 1" not in text

            # Toggle on
            await pilot.press("ctrl+o")
            await pilot.pause()
            text_on = "\n".join(s.text for s in log.lines)
            assert "thought 1" in text_on

            # Toggle off
            await pilot.press("ctrl+o")
            await pilot.pause()
            text_off = "\n".join(s.text for s in log.lines)
            assert "thought 1" not in text_off
            assert "visible line" in text_off


# ── Spinner ──────────────────────────────────────────────────────────


class TestSpinner:
    @pytest.mark.asyncio
    async def test_start_stop(self, app):
        async with app.run_test(headless=True) as pilot:
            app._start_spinner()
            await pilot.pause()
            assert app._spinner_timer is not None

            app._stop_spinner()
            await pilot.pause()
            assert app._spinner_timer is None


# ── Cancel ───────────────────────────────────────────────────────────


class TestCancel:
    @pytest.mark.asyncio
    async def test_escape_cancels_work(self, app):
        import time

        class SlowBackend(DummyBackend):
            def chat(self, message, model, history, status_fn):
                time.sleep(10)
                return super().chat(message, model, history, status_fn)

        async with app.run_test(headless=True) as pilot:
            app.backend = SlowBackend()
            inp = app.query_one("#prompt-input", MonetInput)
            inp.value = "hello"
            await pilot.press("enter")
            await pilot.pause()
            await asyncio.sleep(0.3)

            assert app._spinner_timer is not None
            await pilot.press("escape")
            await pilot.pause()
            await asyncio.sleep(0.2)
            assert app._spinner_timer is None


# ── Banner auto-hide ─────────────────────────────────────────────────


class TestBanner:
    @pytest.mark.asyncio
    async def test_hides_on_overflow(self, app):
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            banner = app.query_one("#banner")
            log = app.query_one("#content", ContentLog)
            for i in range(30):
                log.write(f"line {i}")
            await pilot.pause()
            assert banner.has_class("hidden")


# ── Markdown rendering ───────────────────────────────────────────────


class TestMarkdown:
    @pytest.mark.asyncio
    async def test_code_block(self, app):
        async with app.run_test(headless=True) as pilot:
            log = app.query_one("#content", ContentLog)
            log.clear()
            await pilot.pause()
            app.write_markdown("```python\ndef foo():\n    pass\n```")
            await pilot.pause()
            text = "\n".join(s.text for s in log.lines)
            assert "def foo" in text

    @pytest.mark.asyncio
    async def test_inline_styling(self, app):
        async with app.run_test(headless=True) as pilot:
            log = app.query_one("#content", ContentLog)
            log.clear()
            await pilot.pause()
            app.write_markdown("Some **bold** and `code`")
            await pilot.pause()
            text = "\n".join(s.text for s in log.lines)
            assert "bold" in text
            assert "code" in text

    @pytest.mark.asyncio
    async def test_brackets_escaped(self, app):
        async with app.run_test(headless=True) as pilot:
            log = app.query_one("#content", ContentLog)
            log.clear()
            await pilot.pause()
            app.write_markdown("a [test] bracket")
            await pilot.pause()
            text = "\n".join(s.text for s in log.lines)
            assert "[test]" in text

    @pytest.mark.asyncio
    async def test_blank_lines_preserved(self, app):
        async with app.run_test(headless=True) as pilot:
            log = app.query_one("#content", ContentLog)
            log.clear()
            await pilot.pause()
            app.write_markdown("para one\n\npara two")
            await pilot.pause()
            # Should have at least 3 lines: para one, blank, para two
            assert len(log.lines) >= 3


# ── Trajectory blocks ────────────────────────────────────────────────


class TestTrajectoryBlocks:
    @pytest.mark.asyncio
    async def test_tool_call_block(self, app):
        async with app.run_test(headless=True) as pilot:
            log = app.query_one("#content", ContentLog)
            log.clear()
            await pilot.pause()
            app.show_thinking = True
            app._write_block(
                log,
                ContentBlock(
                    type="toolCall",
                    tool_name="bash",
                    arguments={"command": "ls"},
                ),
            )
            await pilot.pause()
            text = "\n".join(s.text for s in log.lines)
            assert "bash" in text
            assert "ls" in text

    @pytest.mark.asyncio
    async def test_tool_result_block(self, app):
        async with app.run_test(headless=True) as pilot:
            log = app.query_one("#content", ContentLog)
            log.clear()
            await pilot.pause()
            app._write_block(
                log,
                ContentBlock(type="toolResult", content="file.txt"),
            )
            await pilot.pause()
            text = "\n".join(s.text for s in log.lines)
            assert "file.txt" in text

    @pytest.mark.asyncio
    async def test_diff_in_tool_result(self, app):
        async with app.run_test(headless=True) as pilot:
            log = app.query_one("#content", ContentLog)
            log.clear()
            await pilot.pause()
            diff_content = (
                "edited foo.py\n"
                "--- foo.py\n+++ foo.py\n@@ -1 +1 @@\n-old\n+new"
            )
            app._write_block(
                log,
                ContentBlock(type="toolResult", content=diff_content),
            )
            await pilot.pause()
            text = "\n".join(s.text for s in log.lines)
            assert "edited foo.py" in text


# ── Version flag ─────────────────────────────────────────────────────


class TestVersion:
    def test_version_flag(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["monet", "--version"])
        from monet.app import main

        main()
        captured = capsys.readouterr()
        assert "monet" in captured.out
        assert "0.1.0" in captured.out

    def test_v_flag(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["monet", "-v"])
        from monet.app import main

        main()
        captured = capsys.readouterr()
        assert "monet" in captured.out
