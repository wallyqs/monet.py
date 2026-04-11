"""Built-in commands that ship with monet."""

from monet.commands import registry


def _model_handler(app: object, args: str) -> None:
    """Handle /model or /model <name>."""
    from rich.markup import escape
    from monet.providers import provider_by_name

    if not args.strip():
        app._open_model_selector()  # type: ignore[attr-defined]
        return
    name = args.strip()
    provider = provider_by_name(name)
    log = app.query_one("#content")  # type: ignore[attr-defined]
    if provider is None:
        log.write(f"[#E05A3A]unknown model:[/#E05A3A] {escape(name)}")
        return
    app._apply_provider(provider)  # type: ignore[attr-defined]
    log.write(
        f"[#8AB060]switched to[/#8AB060] [b]{escape(provider.model)}[/b] "
        f"[dim]({provider.label})[/dim]"
    )


def register_builtins() -> None:
    """Register all built-in commands."""
    registry.register("/model", "List available models", _model_handler)
