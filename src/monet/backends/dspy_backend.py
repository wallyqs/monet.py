"""DSPy-powered backend.

- ``chat``    → ``dspy.ReAct`` with a ``history`` input field.
- ``predict`` → direct ``lm(prompt=...)`` call.
- ``code``    → ``dspy.ChainOfThought`` over a ``request -> code`` signature.

``dspy`` is imported lazily in ``__init__`` so importing the ``monet.backends``
package for just the Protocol or ``DummyBackend`` does not pull in
dspy/litellm/optuna. Tools passed in here are forwarded to ``dspy.ReAct``.
"""

from typing import Any, Callable

from monet.backends.base import (
    BackendResult,
    ContentBlock,
    LogFunc,
    Message,
    now_iso,
)


class DSPyBackend:
    """Backend that uses dspy.ReAct for chat and dspy.Predict-family for the rest."""

    def __init__(self, tools: list[Callable[..., Any]] | None = None) -> None:
        import dspy  # lazy: heavy import chain (litellm, optuna, …)

        self._dspy = dspy
        self._tools = tools or []
        self._lm_cache: dict[str, Any] = {}
        self._react: Any | None = None
        # Provider-specific overrides, set via configure().
        self._api_base: str = ""
        self._api_key: str = ""

    # ---- configuration ---------------------------------------------------

    def configure(self, *, api_base: str = "", api_key: str = "") -> None:
        """Set provider-specific LM parameters and invalidate the LM cache."""
        self._api_base = api_base
        self._api_key = api_key
        self._lm_cache.clear()

    # ---- helpers --------------------------------------------------------

    def _lm(self, model: str) -> Any:
        if model not in self._lm_cache:
            kwargs: dict[str, Any] = {}
            if self._api_base:
                kwargs["api_base"] = self._api_base
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._lm_cache[model] = self._dspy.LM(model, **kwargs)
        return self._lm_cache[model]

    def _get_react(self) -> Any:
        if self._react is not None:
            return self._react
        dspy = self._dspy

        class ChatSignature(dspy.Signature):  # type: ignore[misc,valid-type]
            """Respond to the user. Use tools when helpful. Maintain context from history.

            When the user asks you to add a slash command to monet code, create a
            Python plugin file at .monet/commands/<name>.py with this structure:

                NAME = "/<name>"
                DESCRIPTION = "<short description>"

                def handler(app, args: str) -> None:
                    log = app.query_one("#content")
                    log.write("output text")

            The handler receives the app instance and args (everything after the
            command name). Use log.write() with Rich markup to produce output.
            After writing the file, call register_command(".monet/commands/<name>.py")
            to activate it immediately.

            Commands can call app.predict(signature, **kwargs) to query the LLM.
            predict() takes a DSPy signature string and returns a dict of output
            field values. Example:

                def handler(app, args: str) -> None:
                    log = app.query_one("#content")
                    result = app.predict("topic -> summary", topic=args.strip())
                    if "error" in result:
                        log.write(f"[red]{result['error']}[/red]")
                    else:
                        log.write(result["summary"])

            Commands can also use standard Python libraries (requests, subprocess,
            json, etc.) to fetch data, then pass it to app.predict() for analysis.

            The app object is a Textual App. Useful attributes and methods:
              - app.query_one("#content")  — the content log, use log.write() for output
              - app.write_markdown(text)   — render markdown with syntax-highlighted code blocks
              - app.predict(sig, **kw)     — call the LLM via dspy.Predict
              - app.model                  — current LiteLLM model string
              - app.current_provider       — Provider with .model, .label
              - app.theme = "name"         — switch Textual UI theme (reactive property)
              - app.available_themes       — dict of available theme names
              - app.history                — list[Message] chat history
            Use Rich markup in log.write(): [bold], [dim], [#F4A300]amber[/], etc.
            """

            history: dspy.History = dspy.InputField(
                desc="Prior turns of the conversation."
            )
            message: str = dspy.InputField(desc="The user's current message.")
            response: str = dspy.OutputField(desc="Assistant reply.")

        self._react = dspy.ReAct(ChatSignature, tools=self._tools)
        return self._react

    def _to_dspy_history(self, history: list[Message]) -> Any:
        """Pair consecutive user/assistant turns into ``{message, response}`` dicts."""
        messages: list[dict[str, str]] = []
        pending_user: str | None = None
        for m in history:
            if m.role == "user":
                pending_user = m.content
            elif m.role == "assistant" and pending_user is not None:
                messages.append({"message": pending_user, "response": m.content})
                pending_user = None
        return self._dspy.History(messages=messages)

    @staticmethod
    def _trajectory_blocks(trajectory: Any) -> list[ContentBlock]:
        """Flatten a ReAct trajectory dict into typed ContentBlocks."""
        blocks: list[ContentBlock] = []
        if not isinstance(trajectory, dict):
            return blocks
        i = 0
        while f"thought_{i}" in trajectory:
            thought = trajectory.get(f"thought_{i}", "")
            if thought:
                blocks.append(ContentBlock(type="thinking", thinking=str(thought)))
            tool_name = trajectory.get(f"tool_name_{i}")
            if tool_name and tool_name != "finish":
                blocks.append(
                    ContentBlock(
                        type="toolCall",
                        tool_name=str(tool_name),
                        arguments=dict(trajectory.get(f"tool_args_{i}") or {}),
                    )
                )
                obs = trajectory.get(f"observation_{i}", "")
                blocks.append(ContentBlock(type="toolResult", content=str(obs)))
            i += 1
        return blocks

    # ---- Backend protocol methods --------------------------------------

    def predict(self, signature: str, model: str, **kwargs: Any) -> dict[str, str]:
        """Run a dspy.Predict call with an arbitrary signature.

        Args:
            signature: DSPy signature string, e.g. "question -> answer".
            model: LiteLLM model identifier.
            **kwargs: Input fields matching the signature.

        Returns:
            Dict mapping output field names to their string values.
            On error, returns {"error": "message"}.
        """
        try:
            lm = self._lm(model)
            predictor = self._dspy.Predict(signature)
            with self._dspy.context(lm=lm):
                result = predictor(**kwargs)
            output_fields = list(predictor.signature.output_fields.keys())
            return {name: str(getattr(result, name, "")) for name in output_fields}
        except Exception as e:
            return {"error": str(e)}

    def code(self, prompt: str, model: str, log_fn: LogFunc) -> BackendResult:
        try:
            log_fn(f"[dspy] code request → {model}")
            lm = self._lm(model)
            predictor = self._dspy.ChainOfThought("request -> code")
            with self._dspy.context(lm=lm):
                result = predictor(request=prompt)
            log_fn("[dspy] code generated")
            code_text = str(getattr(result, "code", ""))
            reasoning = str(getattr(result, "reasoning", ""))
            blocks: list[ContentBlock] = []
            if reasoning:
                blocks.append(ContentBlock(type="thinking", thinking=reasoning))
            blocks.append(ContentBlock(type="text", text=code_text))
            return BackendResult(
                content=code_text,
                timestamp=now_iso(),
                blocks=blocks,
            )
        except Exception as err:  # noqa: BLE001
            return BackendResult(err=err, timestamp=now_iso())

    def chat(
        self,
        message: str,
        model: str,
        history: list[Message],
        status_fn: LogFunc,
    ) -> BackendResult:
        try:
            status_fn(f"[dspy] chat via ReAct → {model}")
            lm = self._lm(model)
            react = self._get_react()
            dspy_history = self._to_dspy_history(history)
            with self._dspy.context(lm=lm):
                result = react(message=message, history=dspy_history)
            reply = str(getattr(result, "response", ""))
            blocks = self._trajectory_blocks(getattr(result, "trajectory", None))
            blocks.append(ContentBlock(type="text", text=reply))
            status_fn("")
            return BackendResult(
                content=reply,
                reply=reply,
                timestamp=now_iso(),
                blocks=blocks,
            )
        except Exception as err:  # noqa: BLE001
            return BackendResult(err=err, timestamp=now_iso())
