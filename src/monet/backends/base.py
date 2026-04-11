"""Core backend types — Protocol, data classes, shared helpers."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Protocol

# Callback for streaming progress or status lines to the UI.
LogFunc = Callable[[str], None]


@dataclass
class Message:
    """A conversation turn for context."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class ContentBlock:
    """Typed content element in a response."""

    type: str  # "text", "thinking", "toolCall", "toolResult"
    text: str = ""
    thinking: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    content: str = ""
    is_error: bool = False


@dataclass
class BackendResult:
    """Result from backend operations."""

    content: str = ""
    timestamp: str = ""
    err: Exception | None = None
    blocks: list[ContentBlock] = field(default_factory=list)
    subject: str = ""  # transport metadata (optional)
    reply: str = ""


class Backend(Protocol):
    """Abstracts the AI assistant service layer."""

    def predict(self, signature: str, model: str, **kwargs: Any) -> dict[str, str]: ...

    def code(self, prompt: str, model: str, log_fn: LogFunc) -> BackendResult: ...

    def chat(
        self,
        message: str,
        model: str,
        history: list[Message],
        status_fn: LogFunc,
    ) -> BackendResult: ...


def now_iso() -> str:
    """ISO-8601 UTC timestamp used by backend results."""
    return datetime.now(UTC).isoformat()
