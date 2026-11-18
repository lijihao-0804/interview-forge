"""Persistent AI chat primitives."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .service import ChatService

__all__ = ["ChatService"]


def __getattr__(name: str):
    # The memory package uses chat.context_blocks without constructing the chat service.
    if name == "ChatService":
        from .service import ChatService
        return ChatService
    raise AttributeError(name)
