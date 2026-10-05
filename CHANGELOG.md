# Changelog

All notable changes to DevAI. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/). Design decisions are numbered in [docs/decisions.md](docs/decisions.md).

## [1.0.0] - 2026-10-05

The first release: every phase of the roadmap, built between 2026-09-29 and 2026-10-05.

### Analysis
- `devai analyze`: files (git, or the filesystem with `.gitignore`), languages, structure, dependency manifests, frameworks, tests and configuration files.
- Findings with severities: missing README or tests, exposed `.env` files, committed secrets (masked), with `--format json` and `--fail-on` for CI.
- `devai review`: checks on the changes about to be committed: secrets in added lines, `.env` files, tests changed with code, debug leftovers, size.

### AI, free models only
- OpenCode's free models through the user's own `opencode` CLI, or a local Ollama; paid models are refused. Anthropic, the first provider, was removed so that nothing could cost money.
- An allow-listed, size-capped context with secrets redacted, shown exactly by `--dry-run`, and consent before anything leaves the machine.
- `--ai` on `analyze` and `review`; `devai chat` with per-question file approval and history; answers grounded in what the model was shown.

### Changes you approve
- `devai fix`: find-and-replace fixes, strictly validated and shown as a diff; `--apply` writes them only after a `y`, with git, staleness and atomic-write checks.
- `devai test`: where tests seem missing, from names alone; `--ai` proposes a new test file, created exclusively after a `y` and never run by DevAI.
- `devai docs`: missing docstrings, JSDoc and README sections, and README commands that would fail; `--ai` writes docstrings proven docs-only by comparing syntax trees, and README sections added without editing a line.

### Web interface
- `devai serve`: a local API (FastAPI) and React pages, reachable from this computer only, locked by a per-run token and Host and Origin checks.
- Every AI task in two clicks to send and two to write, with the same checks as the terminal; Docker image and compose file.
- `DevAI.command`: a double-click launcher for macOS that sets everything up, asks for a project and opens the browser.
- The pages in English and Brazilian Portuguese, with an EN | PT switch.

### GitHub
- `devai pr`, `devai pulls`, `devai issue`, `devai issues` through the `gh` CLI: pull requests reviewed without a checkout, issue plans, and one comment posted only after the user reads it; an allow-list keeps DevAI from merging, closing, approving or creating anything.

### Project
- 900+ automated tests on Python 3.11–3.14 and for the web pages; CI also builds the Docker image and runs DevAI on itself.
- `examples/demo-project` to try every command; [SECURITY.md](SECURITY.md) with the threat model.

[1.0.0]: https://github.com/albanopedro/DevAI/releases/tag/v1.0.0
