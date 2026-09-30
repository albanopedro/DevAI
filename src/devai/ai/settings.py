"""AI settings, read from environment variables only.

DevAI never loads .env files (D026): it runs inside the project it analyzes,
so reading ./.env would mean reading that project's secrets.

DevAI must be free to use (D032). Both providers are free: OpenCode's free
models (run through the user's own `opencode` CLI) and local models (Ollama).
A model that could cost money is rejected here, before anything runs.
"""

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

PROVIDERS = ("opencode", "ollama")
DEFAULT_PROVIDER = "opencode"
DEFAULT_MODELS = {
    "opencode": "opencode/space-bunny-free",  # free, zero data retention
    "ollama": "qwen3.5:9b",
}
DEFAULT_MODEL = DEFAULT_MODELS[DEFAULT_PROVIDER]
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# OpenCode's free models end in "-free", plus a few named exceptions.
OPENCODE_FREE_EXCEPTIONS = frozenset({"big-pickle"})

# Data use of OpenCode's free models, from opencode.ai/docs/zen (prefix → note).
OPENCODE_DATA_NOTES = {
    "space-bunny": None,  # zero retention, no training
    "longcat": None,
    "big-pickle": "this free model may use your data to improve it",
    "mimo-": "this free model may use your data to improve it",
    "ling-": "this free model may use your data to improve it",
    "muse-spark": "this free model may use your data to train future models",
    "nemotron-": "trial model: don't send personal or confidential data",
}


class SettingsError(ValueError):
    """An AI setting has an invalid value; the message is safe to show."""


@dataclass(frozen=True)
class AISettings:
    model: str = DEFAULT_MODEL
    provider: str = DEFAULT_PROVIDER
    ollama_host: str = DEFAULT_OLLAMA_HOST  # Ollama only

    @property
    def leaves_machine(self) -> bool:
        """True if the context would be sent to another computer (D031)."""
        if self.provider == "ollama":
            return not is_loopback(self.ollama_host)
        return True  # OpenCode sends it to its cloud service

    @property
    def destination(self) -> str:
        """Where the context goes, as shown in the consent question."""
        if self.provider == "ollama":
            return f"Ollama at {self.ollama_host} ({self.model})"
        return f"OpenCode ({self.model}, free model)"

    @property
    def data_note(self) -> str | None:
        """What the provider may do with the data, when worth a warning."""
        if self.provider != "opencode":
            return None
        name = self.model.removeprefix("opencode/")
        for prefix, note in OPENCODE_DATA_NOTES.items():
            if name.startswith(prefix):
                return note
        return "check this free model's data policy at opencode.ai/docs/zen"


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
    if chosen == "opencode":
        model = free_opencode_model(model)

    return AISettings(
        model=model,
        provider=chosen,
        ollama_host=ollama_base_url(environ.get("OLLAMA_HOST", "")),
    )


def free_opencode_model(model: str) -> str:
    """Return "opencode/<name>" for a free OpenCode model; reject anything else.

    Only OpenCode's own free models are allowed: another provider configured
    in the user's OpenCode (or a paid model) could cost money.
    """
    provider, separator, name = model.partition("/")
    if not separator:
        provider, name = "opencode", model  # "space-bunny-free" → opencode/...
    if provider != "opencode" or not is_free_opencode_name(name):
        raise SettingsError(
            f"DevAI only uses OpenCode's free models, so it can never cost anything "
            f"(got {model!r}). Pick a model ending in '-free' or big-pickle."
        )
    return f"opencode/{name}"


def is_free_opencode_name(name: str) -> bool:
    return name.endswith("-free") or name in OPENCODE_FREE_EXCEPTIONS


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
