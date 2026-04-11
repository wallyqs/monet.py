"""Backend abstractions for AI assistant services.

Public API is re-exported from the submodules so callers can write
``from monet.backends import Backend, DummyBackend, DSPyBackend, Message``
without caring about the package layout.
"""

from monet.backends.base import (
    Backend,
    BackendResult,
    ContentBlock,
    LogFunc,
    Message,
)
from monet.backends.dspy_backend import DSPyBackend
from monet.backends.dummy import DummyBackend

__all__ = [
    "Backend",
    "BackendResult",
    "ContentBlock",
    "DSPyBackend",
    "DummyBackend",
    "LogFunc",
    "Message",
]
