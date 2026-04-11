"""Tests for the command registry and plugin loading."""

import textwrap

import pytest

from monet.commands import CommandRegistry


@pytest.fixture
def reg():
    return CommandRegistry()


# ── Registry CRUD ────────────────────────────────────────────────────


class TestRegistry:
    def test_register_and_list(self, reg):
        reg.register("/hello", "Say hello", lambda app, args: None)
        commands = reg.list_commands()
        assert commands == [("/hello", "Say hello")]

    def test_register_auto_prefix(self, reg):
        reg.register("hello", "Say hello", lambda app, args: None)
        assert reg.get("/hello") is not None

    def test_unregister(self, reg):
        reg.register("/hello", "Say hello", lambda app, args: None)
        assert reg.unregister("/hello") is True
        assert reg.list_commands() == []

    def test_unregister_missing(self, reg):
        assert reg.unregister("/nope") is False

    def test_dispatch(self, reg):
        results = []
        reg.register("/greet", "Greet", lambda app, args: results.append(args))
        assert reg.dispatch(None, "/greet wally") is True
        assert results == ["wally"]

    def test_dispatch_no_args(self, reg):
        results = []
        reg.register("/ping", "Ping", lambda app, args: results.append(args))
        assert reg.dispatch(None, "/ping") is True
        assert results == [""]

    def test_dispatch_unknown(self, reg):
        assert reg.dispatch(None, "/unknown") is False

    def test_replace(self, reg):
        reg.register("/x", "First", lambda app, args: None)
        reg.register("/x", "Second", lambda app, args: None)
        assert reg.get("/x").description == "Second"
        assert len(reg.list_commands()) == 1


# ── Plugin loading ───────────────────────────────────────────────────


class TestPluginLoading:
    def test_load_valid(self, reg, tmp_path):
        plugin = tmp_path / "greet.py"
        plugin.write_text(
            textwrap.dedent("""\
            NAME = "/greet"
            DESCRIPTION = "Greet someone"

            def handler(app, args):
                pass
        """)
        )
        err = reg.load_plugin(str(plugin))
        assert err is None
        assert reg.get("/greet") is not None
        assert reg.get("/greet").description == "Greet someone"

    def test_load_missing_file(self, reg):
        err = reg.load_plugin("/nonexistent/plugin.py")
        assert err is not None
        assert "not found" in err

    def test_load_missing_name(self, reg, tmp_path):
        plugin = tmp_path / "bad.py"
        plugin.write_text("DESCRIPTION = 'x'\ndef handler(app, args): pass\n")
        err = reg.load_plugin(str(plugin))
        assert err is not None
        assert "invalid plugin" in err

    def test_load_missing_handler(self, reg, tmp_path):
        plugin = tmp_path / "bad2.py"
        plugin.write_text('NAME = "/x"\nDESCRIPTION = "x"\n')
        err = reg.load_plugin(str(plugin))
        assert err is not None
        assert "invalid plugin" in err

    def test_load_syntax_error(self, reg, tmp_path):
        plugin = tmp_path / "broken.py"
        plugin.write_text("def handler(:\n")
        err = reg.load_plugin(str(plugin))
        assert err is not None
        assert "error" in err

    def test_reload(self, reg, tmp_path):
        # Use a unique filename to avoid sys.modules collisions
        import uuid

        name = f"reload_{uuid.uuid4().hex[:8]}"
        plugin = tmp_path / f"{name}.py"
        plugin.write_text(
            'NAME = "/count"\nDESCRIPTION = "Version 1"\n\ndef handler(app, args):\n    pass\n'
        )
        err = reg.load_plugin(str(plugin))
        assert err is None
        assert reg.get("/count").description == "Version 1"

        # Update and reload
        plugin.write_text(
            'NAME = "/count"\nDESCRIPTION = "Version 2"\n\ndef handler(app, args):\n    pass\n'
        )
        err = reg.load_plugin(str(plugin))
        assert err is None
        assert reg.get("/count").description == "Version 2"

    def test_load_all_plugins(self, reg, tmp_path, monkeypatch):
        # Create plugins in a temp dir
        (tmp_path / "a.py").write_text(
            'NAME = "/aaa"\nDESCRIPTION = "A"\ndef handler(app, args): pass\n'
        )
        (tmp_path / "b.py").write_text(
            'NAME = "/bbb"\nDESCRIPTION = "B"\ndef handler(app, args): pass\n'
        )
        # _builtins should be skipped
        (tmp_path / "_hidden.py").write_text(
            'NAME = "/hidden"\nDESCRIPTION = "H"\ndef handler(app, args): pass\n'
        )

        monkeypatch.setattr("monet.commands.USER_COMMANDS_DIR", tmp_path)
        errors = reg.load_all_plugins()
        assert errors == []
        names = [n for n, _ in reg.list_commands()]
        assert "/aaa" in names
        assert "/bbb" in names
        assert "/hidden" not in names


# ── register_command tool ────────────────────────────────────────────


class TestRegisterCommandTool:
    def test_tool_registers(self, tmp_path):
        from monet.tools import register_command

        plugin = tmp_path / "tool_test.py"
        plugin.write_text(
            textwrap.dedent("""\
            NAME = "/tool-test"
            DESCRIPTION = "Tool test"

            def handler(app, args):
                pass
        """)
        )
        result = register_command(str(plugin))
        assert "registered" in result

    def test_tool_error(self):
        from monet.tools import register_command

        result = register_command("/nonexistent.py")
        assert result.startswith("error:")

    def test_tool_empty_path(self):
        from monet.tools import register_command

        result = register_command("")
        assert result.startswith("error:")
