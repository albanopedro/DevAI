"""`devai chat`: questions about a project, answered with selected files.

Phase 5a: local file selection and the context preview (--dry-run).
"""

from devai.chat.context import build_chat_context
from devai.chat.retrieval import ChatError, Selection, select_files

__all__ = ["ChatError", "Selection", "build_chat_context", "select_files"]
