"""`devai chat`: questions about a project, answered with files the user approves.

Files are chosen locally (keyword search or --file) and shown before they are
sent; answers are grounded in the lines that were sent (D039-D041).
"""

from devai.chat.context import build_chat_context
from devai.chat.retrieval import ChatError, Selection, select_files

__all__ = ["ChatError", "Selection", "build_chat_context", "select_files"]
