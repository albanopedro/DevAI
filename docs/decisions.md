# Design Decisions

Short records of important decisions. Each one gives the decision, why it was made, and what else was considered.
New decisions are appended; superseded ones are marked, not deleted.

---

## D001: Deterministic analysis first, AI opt-in

- **Decision:** `devai analyze` runs fully offline and produces a structured report. AI interpretation is enabled explicitly (`--ai`) and reads that report, not the raw repository.
- **Why:** Privacy (no code leaves the machine by default), cost, and testability (deterministic code can be tested exactly). Most basic findings, such as missing tests, missing README or exposed keys, don't need an LLM.
- **Alternatives:** Send project files straight to an LLM. That is simpler at first, but it is expensive, non-deterministic, and leaks code by default.

## D002: Python ≥ 3.11

- **Decision:** Require Python 3.11 or newer.
- **Why:** `tomllib` (reading `pyproject.toml` files, needed in Phase 2) is in the standard library from 3.11. Development machine runs 3.14.
- **Alternatives:** 3.10 plus the `tomli` package. That adds a dependency for no real gain.

## D003: CLI built with `argparse`

- **Decision:** Use the standard library `argparse`.
- **Why:** No dependency, and it teaches CLI fundamentals. The CLI layer stays thin (parse args → call core → print), so switching later is cheap.
- **Alternatives:** Typer (less boilerplate, type-hint based, extra dependency) and Click (the base Typer builds on). Worth revisiting if subcommands become hard to maintain.

## D004: `src/` layout, packaging via `pyproject.toml`, venv + pip

- **Decision:** Code lives in `src/devai/`. The project is installed in editable mode (`pip install -e .`) inside a standard `venv`.
- **Why:** The `src/` layout forces tests to run against the installed package, which avoids accidental imports from the working directory. venv and pip ship with Python.
- **Alternatives:** Flat layout (simpler, but hides packaging mistakes); uv or Poetry (faster and richer, but extra tools to learn and install).

## D005: Start with modules, promote to packages when they grow

- **Decision:** Phase 1 uses single modules (`cli.py`, `scanner.py`, `models.py`). A module becomes a package (for example `analyzer/`) only when it outgrows one file.
- **Why:** Empty folders with one file each are structure without content. Growing on demand keeps the architecture honest.
- **Alternatives:** Create the full tree (`cli/`, `analyzer/`, `ai/`, `git/`, `core/`) up front.

## D006: Dataclasses now, Pydantic when validating external data

- **Decision:** Internal data models use `dataclasses`. Pydantic is introduced in Phase 3 to validate LLM responses (and later API payloads).
- **Why:** Pydantic's strength is validating untrusted input. Internal data doesn't need it yet.
- **Alternatives:** Pydantic from day one. It works, but adds a dependency before there's a problem for it to solve.

## D007: Git via `subprocess`, not GitPython

- **Decision:** Call the `git` binary with `subprocess.run` when Git data is needed (Phase 2+).
- **Why:** GitPython itself shells out to `git`. For `status`, `diff`, `log` and `ls-files`, direct calls are simpler, more transparent, and dependency-free.
- **Alternatives:** GitPython, which is worth reconsidering if Git interaction becomes complex.

## D008: DevAI never commits, pushes, merges or rewrites history

- **Decision:** DevAI (and its development process) may read Git state and suggest commands or commit messages, but never runs `commit`, `push`, `merge`, `rebase`, `reset --hard` or `clean`.
- **Why:** Git history is the user's responsibility. Destructive or outward-facing actions need a human.

## D009: Findings as a core data model

- **Decision:** Every detected problem is a `Finding` with `rule_id`, `severity`, `message`, optional `file`/`line`, and masked `evidence`. Introduced in Phase 2.
- **Why:** One shape feeds the terminal report, JSON output, CI exit codes, tests and the AI context builder.

## D010: Secrets are always masked

- **Decision:** Any detected secret is shown masked (for example `sk-a…****`). `.env` file contents are never read into reports or AI context.
- **Why:** A security tool must not become the leak it reports.

## D011: Roadmap changes from the original spec

- Phase 2 split into **2a** (scanner) and **2b** (checks), because the original phase was too large.
- **CI** (GitHub Actions) moved right after Phase 1. **Docker** moved to the web phase, where it adds value.
- **Local AI (Ollama)** moved to right after Phase 3 to validate the LLM client abstraction and allow free, private experimentation.
- **JSON output and exit codes** added in Phase 2b so DevAI is usable in CI.

## D012: Language and license

- **Decision:** Code, docs and CLI messages in English. MIT license.
- **Why:** Broader reach as a portfolio project; MIT is simple and permissive.

## D013: CI on GitHub Actions, Ubuntu, Python 3.11–3.14

- **Decision:** One workflow runs lint, format check and tests on every push to `main` and every pull request, on Ubuntu, across Python 3.11–3.14. Actions are pinned to major versions (`@v4`, `@v5`).
- **Why:** 3.11 is the minimum promised in `pyproject.toml` and 3.14 is the development version, so the matrix proves both ends. Ubuntu alone is enough for now. Windows is excluded because creating symlinks (used in a test) needs extra privileges there.
- **Alternatives:** Pinning actions by commit SHA (safer against a compromised action, harder to maintain); adding macOS and Windows runners (more coverage, slower, not needed yet).

## D014: Ruff for linting and formatting

- **Decision:** Use Ruff (`ruff check` + `ruff format`) with rules `E`, `F`, `I`, `UP`, `B`, enforced in CI.
- **Why:** One fast tool replaces flake8, black and isort. The rule set stays small: real errors, import order, modern syntax and common bug patterns, without stylistic nitpicks.
- **Alternatives:** flake8 + black + isort (three tools, slower); no linter (inconsistent style over time).
