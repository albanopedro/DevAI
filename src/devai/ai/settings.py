"""AI settings, read from environment variables only.

DevAI never loads .env files (D026): it runs inside the project it analyzes,
so reading ./.env would mean reading that project's secrets.
"""

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

PROVIDERS = ("anthropic", "ollama")
DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "ollama": "qwen3.5:9b"}
DEFAULT_MODEL = DEFAULT_MODELS[DEFAULT_PROVIDER]
DEFAULT_EFFORT = "medium"
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


class SettingsError(ValueError):
    """An AI setting has an invalid value; the message is safe to show."""


@dataclass(frozen=True)
class AISettings:
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT  # Anthropic only
    provider: str = DEFAULT_PROVIDER
    ollama_host: str = DEFAULT_OLLAMA_HOST  # Ollama only

    @property
    def leaves_machine(self) -> bool:
        """True if the context would be sent to another computer (D031)."""
        if self.provider == "ollama":
            return not is_loopback(self.ollama_host)
        return True

    @property
    def destination(self) -> str:
        """Where the context goes, as shown in the consent question."""
        if self.provider == "ollama":
            return f"Ollama at {self.ollama_host} ({self.model})"
        return f"Anthropic ({self.model})"


def load_settings(
    environ: Mapping[str, str] = os.environ, provider: str | None = None
) -> AISettings:
    """Read settings; `provider` (from --provider) wins over DEVAI_AI_PROVIDER."""
    chosen = provider or environ.get("DEVAI_AI_PROVIDER", "")
    chosen = chosen.strip().lower() or DEFAULT_PROVIDER
    if chosen not in PROVIDERS:
        names = ", ".join(PROVIDERS)
        raise SettingsError(
            f"DEVAI_AI_PROVIDER must be one of {names} (got {chosen!r})"
        )

    model = environ.get("DEVAI_AI_MODEL", "").strip() or DEFAULT_MODELS[chosen]
    effort = environ.get("DEVAI_AI_EFFORT", "").strip().lower() or DEFAULT_EFFORT
    if effort not in EFFORT_LEVELS:
        levels = ", ".join(EFFORT_LEVELS)
        raise SettingsError(f"DEVAI_AI_EFFORT must be one of {levels} (got {effort!r})")

    return AISettings(
        model=model,
        effort=effort,
        provider=chosen,
        ollama_host=ollama_base_url(environ.get("OLLAMA_HOST", "")),
    )


def ollama_base_url(value: str) -> str:
    """Normalize OLLAMA_HOST with the same rules as Ollama itself.

    "gpu-box" → http://gpu-box:11434, "http://gpu-box" → port 80,
    "https://gpu-box" → port 443, empty → http://localhost:11434.
    """
    value = value.strip()
    if not value:
        return DEFAULT_OLLAMA_HOST

    scheme, separator, _ = value.partition("://")
    if not separator:
        scheme, value, default_port = "http", f"http://{value}", 11434
    else:
        default_port = {"http": 80, "https": 443}.get(scheme.lower())
    if default_port is None:
        raise SettingsError(f"OLLAMA_HOST must use http or https (got {scheme!r})")

    try:
        parts = urlsplit(value)
        port = parts.port or default_port
    except ValueError as error:
        raise SettingsError(f"OLLAMA_HOST is not a valid address: {value!r}") from error
    host = parts.hostname
    if not host:
        raise SettingsError(f"OLLAMA_HOST is not a valid address: {value!r}")
    if ":" in host:
        host = f"[{host}]"  # IPv6 literal
    return f"{scheme.lower()}://{host}:{port}"


def is_loopback(base_url: str) -> bool:
    """True if `base_url` points at this computer."""
    host = urlsplit(base_url).hostname or ""
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False  # any other name may resolve to another machine
    # 0.0.0.0 is Ollama's "all interfaces" bind address; clients reach this machine.
    return address.is_loopback or address.is_unspecified
