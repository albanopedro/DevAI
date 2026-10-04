"""AI support shared by every command: context, settings, clients, results.

Only free models are used: OpenCode's free models through the local
`opencode` CLI, or a local Ollama. Nothing is sent before the user agrees.
"""

from devai.ai.context import build_context, estimate_tokens, serialize_context

__all__ = ["build_context", "estimate_tokens", "serialize_context"]
