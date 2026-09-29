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

## D015: File listing via git first, filesystem walk as fallback

- **Decision:** Inside a git work tree, list files with `git ls-files --cached --others --exclude-standard -z`. Otherwise (or if git fails), walk the filesystem, skip a fixed set of generated directories and apply the root `.gitignore`.
- **Why:** Git's own listing is exact by definition. It honors nested `.gitignore` files, `.git/info/exclude`, the global excludes file, and keeps tracked files that match an ignore pattern. The fallback covers projects without git, such as a downloaded ZIP that still carries its `.gitignore`.
- **Alternatives:** Always use the filesystem walk with pathspec. That is one code path, but it misses nested and global rules. Filesystem walk only, with no `.gitignore` support: generated and editor folders inflate the counts (51 of 110 files in a real test project).
- **Consequence:** The user's global excludes file affects results, as it does `git status`. Tests isolate `HOME`/`XDG_CONFIG_HOME` for this reason.

## D016: pathspec for `.gitignore` matching

- **Decision:** Use `pathspec` (`GitIgnoreSpec`), the first runtime dependency.
- **Why:** Gitignore semantics are subtle: negation (`!`), anchoring (`/build`), directory-only patterns (`logs/`), `**`. pathspec implements git's behavior, is pure Python, and has no dependencies of its own.
- **Alternatives:** A hand-written matcher on `fnmatch` (error-prone, and mistakes silently skew results); no `.gitignore` support in the fallback.

## D017: Languages by file extension, counted in files

- **Decision:** Map extensions to languages with a plain dictionary and count files per language. Data and docs formats are excluded. `.jsx`/`.tsx` count as JavaScript/TypeScript.
- **Why:** Simple, predictable and fast, with no need to read file contents.
- **Alternatives:** Count bytes or lines, as GitHub Linguist does. That is more representative, but lines require reading every file, and extensions are ambiguous in some cases (`.h`). Content-based detection is a possible later improvement.

## D018: Phase 2b split into stack detection (2b) and findings (2c)

- **Decision:** 2b only describes the stack. Judging it (findings, severities, secret scanning, JSON output, exit codes) moves to 2c.
- **Why:** Secret scanning is the first step that reads source file contents, a privacy boundary that deserves its own phase and decisions. Smaller phases are also easier to review.
- **Consequence:** In 2b the only files opened are dependency manifests (and `.gitignore`, from 2a). Parse warnings report the error position, never file contents.

## D019: PEP 508 names extracted with a regex, not `packaging`

- **Decision:** Read the leading name of each requirement with a small regex and normalize it per PEP 503 (`Flask_SQLAlchemy` → `flask-sqlalchemy`). URL-only and local-path requirements are skipped.
- **Why:** Detection only needs the package name, not versions or markers. That avoids a dependency.
- **Alternatives:** `packaging.requirements.Requirement` (a complete PEP 508 parser, one more dependency). Revisit if a real project exposes a case the regex gets wrong.

## D020: Frameworks and test files by simple, explicit rules

- **Decision:** Frameworks come from a per-ecosystem table of dependency names; test files from naming conventions and test directories, counting source files only; config files from a list of well-known names.
- **Why:** Predictable, easy to test and extend with one line. The tables are per ecosystem, so an npm name never matches a Python package.
- **Alternatives:** Content-based detection (imports, config file contents). More accurate, but it needs to read source code, which is out of scope for 2b (D018).
- **Known limits:** Poetry's `[tool.poetry.dependencies]` isn't read. `unittest`-only Python projects show test files but no test framework, because unittest is in the standard library.
