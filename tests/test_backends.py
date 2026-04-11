"""Tests for backend protocol, DummyBackend, and base types."""

from monet.backends.base import BackendResult, ContentBlock, Message, now_iso
from monet.backends.dummy import DummyBackend


# ── Data types ───────────────────────────────────────────────────────


class TestMessage:
    def test_fields(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"


class TestContentBlock:
    def test_defaults(self):
        b = ContentBlock(type="text")
        assert b.text == ""
        assert b.thinking == ""
        assert b.tool_name == ""
        assert b.arguments == {}
        assert b.content == ""
        assert b.is_error is False

    def test_thinking(self):
        b = ContentBlock(type="thinking", thinking="reasoning here")
        assert b.type == "thinking"
        assert b.thinking == "reasoning here"

    def test_tool_call(self):
        b = ContentBlock(
            type="toolCall", tool_name="bash", arguments={"command": "ls"}
        )
        assert b.tool_name == "bash"
        assert b.arguments == {"command": "ls"}

    def test_tool_result_error(self):
        b = ContentBlock(type="toolResult", content="not found", is_error=True)
        assert b.is_error is True
        assert b.content == "not found"


class TestBackendResult:
    def test_defaults(self):
        r = BackendResult()
        assert r.content == ""
        assert r.err is None
        assert r.blocks == []
        assert r.reply == ""

    def test_with_error(self):
        e = ValueError("boom")
        r = BackendResult(err=e)
        assert r.err is e

    def test_with_blocks(self):
        blocks = [ContentBlock(type="text", text="hi")]
        r = BackendResult(content="hi", blocks=blocks)
        assert len(r.blocks) == 1
        assert r.blocks[0].text == "hi"

    def test_mutable_defaults_isolated(self):
        r1 = BackendResult()
        r2 = BackendResult()
        r1.blocks.append(ContentBlock(type="text"))
        assert len(r2.blocks) == 0


class TestNowIso:
    def test_format(self):
        ts = now_iso()
        assert "T" in ts
        assert "+" in ts or "Z" in ts


# ── DummyBackend ─────────────────────────────────────────────────────


class TestDummyBackendPredict:
    def test_single_output(self):
        b = DummyBackend()
        r = b.predict("question -> answer", "test", question="what?")
        assert "answer" in r
        assert "question" not in r
        assert "what?" in r["answer"]

    def test_multiple_outputs(self):
        b = DummyBackend()
        r = b.predict("data -> summary, sentiment", "m", data="good stuff")
        assert "summary" in r
        assert "sentiment" in r

    def test_no_arrow(self):
        b = DummyBackend()
        r = b.predict("question", "m", question="hi")
        assert "question" in r

    def test_model_in_response(self):
        b = DummyBackend()
        r = b.predict("q -> a", "my-model", q="x")
        assert "my-model" in r["a"]


class TestDummyBackendCode:
    def test_basic(self):
        b = DummyBackend()
        logs = []
        r = b.code("fizzbuzz", "m", logs.append)
        assert r.content.startswith("#")
        assert "fizzbuzz" in r.content
        assert len(r.blocks) == 1
        assert r.blocks[0].type == "text"
        assert len(logs) == 2

    def test_timestamp(self):
        b = DummyBackend()
        r = b.code("x", "m", lambda _: None)
        assert r.timestamp != ""


class TestDummyBackendChat:
    def test_basic(self):
        b = DummyBackend()
        logs = []
        r = b.chat("hello", "m", [], logs.append)
        assert "hello" in r.reply
        assert r.reply == r.content
        assert len(r.blocks) == 1
        assert r.blocks[0].type == "text"

    def test_history_count(self):
        b = DummyBackend()
        logs = []
        history = [
            Message(role="user", content="x"),
            Message(role="assistant", content="y"),
        ]
        b.chat("hi", "m", history, logs.append)
        assert "2 prior turns" in logs[0]

    def test_model_in_reply(self):
        b = DummyBackend()
        r = b.chat("hi", "cool-model", [], lambda _: None)
        assert "cool-model" in r.reply
