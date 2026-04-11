"""Stub backend that echoes inputs. Useful for UI development and tests."""

from typing import Any

from monet.backends.base import (
    BackendResult,
    ContentBlock,
    LogFunc,
    Message,
    now_iso,
)


class DummyBackend:
    """In-memory backend that fabricates deterministic replies."""

    def predict(self, signature: str, model: str, **kwargs: Any) -> dict[str, str]:
        # Parse output field names from the signature (e.g. "topic -> summary")
        if "->" in signature:
            output_part = signature.split("->", 1)[1].strip()
            output_fields = [f.strip() for f in output_part.split(",")]
        else:
            output_fields = list(kwargs.keys())
        input_text = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        return {name: f"[dummy:{model}] {input_text}" for name in output_fields}

    def code(self, prompt: str, model: str, log_fn: LogFunc) -> BackendResult:
        log_fn(f"[dummy] coding with model={model}")
        log_fn(f"[dummy] prompt: {prompt}")
        content = f"# dummy code response for: {prompt}\npass\n"
        return BackendResult(
            content=content,
            timestamp=now_iso(),
            blocks=[ContentBlock(type="text", text=content)],
        )

    def chat(
        self,
        message: str,
        model: str,
        history: list[Message],
        status_fn: LogFunc,
    ) -> BackendResult:
        status_fn(f"[dummy] chat ({len(history)} prior turns)")
        reply = f"[dummy:{model}] echo: {message}"
        return BackendResult(
            content=reply,
            reply=reply,
            timestamp=now_iso(),
            blocks=[ContentBlock(type="text", text=reply)],
        )
