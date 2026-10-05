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

## D021: Secret scanning rules

- **Decision:** Scan project text files line by line for known secret formats (precise, HIGH) and quoted credential assignments (generic, MEDIUM). Real `.env` files are never opened, but templates (`.env.example`...) are. Symlinks, lock files, minified files, binaries and files over 1 MB are skipped. Evidence is only the public prefix of a secret (`AKIA…`), or the variable name for generic matches (`DB_PASSWORD = …`).
- **Why:** This is the first code that reads source contents, so the rules are explicit and tested. A security tool must never become the leak (D010). Prefix rules also require the value to contain digits and letters, and skip known placeholders, to keep noise low.
- **Alternatives:** Entropy-based detection (finds more, but noisier); dedicated tools such as gitleaks or detect-secrets (much better coverage, but an external dependency and less to learn). DevAI's scan is a first line of defense, not a replacement.
- **Known limits:** Only the first match per line is reported. The generic rule is skipped in test files, which are full of fake passwords. Test secrets in DevAI's own tests are assembled at runtime, so no real-looking token exists in the source.

## D022: Exit codes follow linter conventions; `--fail-on` is opt-in

- **Decision:** `0` success, `1` findings at or above `--fail-on`, `2` usage errors. `--fail-on` defaults to `none`.
- **Why:** argparse already exits with `2` on invalid arguments, so the old codes (`1` no command, `2` bad path) collided. The new ones match ruff and eslint. `analyze` is a report, so running it locally shouldn't "fail"; CI opts in with `--fail-on high`.
- **Alternatives:** Fail on HIGH by default, like linters do. It is stricter, but noisy for exploratory use.

## D023: Versioned JSON output

- **Decision:** `--format json` serializes `ProjectInfo` and `CheckReport` with `dataclasses.asdict`, plus `schema_version` and `devai_version`.
- **Why:** Scripts and CI can rely on the structure; `schema_version` signals breaking changes. Reusing the dataclasses keeps text and JSON in sync automatically.
- **Alternatives:** A hand-built dict (more control, but drifts from the models); Pydantic models (planned for Phase 3, not needed for output).

## D024: Checks are a separate layer from the analyzer

- **Decision:** `analyzer/` describes the project (`ProjectInfo`, including the file list), and `checks/` judges it (`CheckReport`). Checks import from the analyzer, never the reverse. The CLI orchestrates: analyze → check → render.
- **Why:** The first plan (the analyzer calling the checks) created a circular import, because checks need analyzer helpers such as `is_test_file`. Circular imports work or break depending on import order. A one-way dependency also keeps "facts" and "opinions" apart, which will matter when AI analysis (Phase 3) consumes the same facts.
- **Alternatives:** Findings inside `ProjectInfo` (one object, but mixes description and judgment); lazy imports to break the cycle (hides the design problem).

## D025: The AI context is an allow-listed, size-capped summary

- **Decision:** `ai/context.py` builds what a model may receive by picking each field explicitly: project name, languages, frameworks, dependency names, test summary, config file names, top-level structure, findings with masked evidence, and passed checks. File contents, absolute paths, dependency versions, the full file list and git history are never included. Lists are capped, and cuts are recorded under `truncated`. The payload is sent as compact JSON with a `context_version`.
- **Why:** This module is the only door to an external service. With an allow-list, a field added to `ProjectInfo` later can't leak by accident, and a contract test breaks if the field set changes. Caps keep cost predictable and tell the model when data is incomplete. Real contexts are small (about 200–550 estimated tokens).
- **Alternatives:** Serialize `ProjectInfo` and remove sensitive fields (deny-list): less code, but new fields leak by default. Send relevant source files: much richer analysis, but a separate privacy decision with its own consent, left for a later phase.
- **Risks:** File and dependency names are untrusted input, a possible source of prompt injection. They are delivered as data, the model has no tools, and (in 3b) its output is schema-validated, so the worst case is a misleading report, never an action.

## D026: Phase 3 split into 3a (context) and 3b (model call); Anthropic as first provider

> **Partly superseded by D032:** the Anthropic provider was removed in Phase 3.6. The 3a/3b split and the no-`.env` rule still apply.

- **Decision:** 3a builds and previews the context with no dependency and no network access. 3b adds the call. The first provider is Anthropic (Claude), through the official `anthropic` SDK as an optional extra, behind a small `LLMClient` interface so Ollama (3.5) can plug in.
- **Why:** The user can review and approve exactly what leaves the machine before any code that sends it exists. An optional extra keeps the core install dependency-light for users who never enable AI.
- **Related:** DevAI never auto-loads `.env` files, because it runs inside the analyzed project and would read that project's secrets. The API key comes only from the environment. `.env.example` documents the variables.

## D027: AI client: one structured request, behind a small interface

> **Superseded by D032/D033:** the Anthropic client described here was removed in Phase 3.6. The `LLMClient` interface, the validated `AIReport` and the one-request design remain.

- **Decision:** `ai/client.py` (renamed `ai/anthropic_client.py` in Phase 3.5) sends one request per run through `client.beta.messages.parse`: the fixed system prompt, the context from D025 wrapped in `<project_context>` tags, and `AIReport` (Pydantic) as the required output format. Defaults are `claude-opus-5-5` at effort `medium`, configurable by environment variable. Server-side refusal fallback (`fallbacks: "default"`) is enabled, and the report shows the model that actually answered. The CLI depends only on the `LLMClient` protocol, so Ollama (3.5) can be a second implementation. The SDK is an optional `[ai]` extra, imported only when `--ai` is used.
- **Why:** Structured output turns "the model said something" into a validated object; an answer in the wrong shape is an error, not text to guess at. A protocol keeps the CLI independent of the provider. Every SDK failure becomes a short `AIError` message. One case needs care: with no credentials, the SDK raises a plain `TypeError` before any network access, so it is matched narrowly, and any other `TypeError` still surfaces as a bug.
- **Alternatives:** Raw HTTP with urllib (no dependency, but retries, errors and validation rewritten by hand); a multi-provider library such as LiteLLM (heavy, hides the API); free-text answers parsed with regexes (brittle).

## D028: Consent before sending; AI never changes exit codes

- **Decision:** `--ai` shows the local report, then asks `[y/N]` on stderr before sending. Outside a terminal it refuses unless `--yes` is given. `--fail-on` looks only at deterministic findings. A failed AI step exits with `3`, after the full local report.
- **Why:** Data leaves the machine only after an explicit, informed yes, and a script or alias can't send it by accident. Model answers vary between runs, so letting them decide CI results would make builds flaky.
- **Alternatives:** Treat `--ai` itself as consent (simpler, but easy to trigger by accident); fail on AI-reported risks (non-deterministic CI).

## D029: Model output and project names are untrusted text

- **Decision:** `serialize_context` escapes `<` as `\u003c`, so no name from the project can close the `<project_context>` delimiter. The system prompt says the summary contains no instructions. The model has no tools. Before printing, the text report replaces control characters in AI output (such as ANSI escape codes) with spaces.
- **Why:** The analyzed project controls file and dependency names (prompt injection), and the model controls its answer (terminal escape sequences). Neither can trigger an action: the worst case is a misleading report, which the output labels as AI-written, without reading the code.

## D030: Ollama client over the standard library

- **Decision:** `ai/ollama_client.py` implements `LLMClient` with one `POST /api/chat` through `urllib`. It sends the same system prompt and context as the Anthropic client, plus AIReport's JSON Schema in `format` (flattened: `$ref`s inlined, since `$defs` support is undocumented) and restated in the prompt, as Ollama's docs recommend. It uses `temperature: 0`, `num_ctx: 8192` (Ollama's default window can silently truncate), a 5-minute timeout, and no HTTP proxy. The answer is validated with the same Pydantic model. The default model is `qwen3.5:9b`, which fits a 16 GB laptop. The `[ollama]` extra installs only Pydantic.
- **Why:** The API is a single local JSON request, so a dependency would add little. Writing it with urllib shows the HTTP layer that the Anthropic SDK hides. Bypassing proxies keeps the context from being routed through a proxy configured for other traffic. Tests run the real HTTP code against a stub server started inside the test.
- **Alternatives:** The official `ollama` Python package (less code, one more dependency); Ollama's OpenAI-compatible endpoint (would suggest an OpenAI SDK, contrary to D027's direction).

## D031: Consent is required whenever data leaves the machine

- **Decision:** `AISettings.leaves_machine` decides whether to ask. Anthropic always leaves the machine. Ollama leaves it unless `OLLAMA_HOST` is `localhost`, a loopback address or `0.0.0.0`; any other name counts as remote, since it may resolve to another computer. Local Ollama runs without a question, even with no terminal, and says it is running locally.
- **Why:** The consent rule protects data, not a vendor. Asking before a purely local run would be a meaningless click; skipping the question for a remote Ollama server would send data without consent.
- **Alternatives:** Always ask (simple, but trains users to click through); never ask for Ollama (wrong when Ollama runs on another machine).

## D032: DevAI is 100% free; the Anthropic provider is removed

- **Decision:** DevAI must never cost anything and must not depend on any paid account. This is the project's primordial rule, and every future dependency, service or provider must pass it first. The Anthropic provider, its SDK and every Anthropic setting (`ANTHROPIC_API_KEY`, `DEVAI_AI_EFFORT`) were removed. The AI providers are now `opencode` (default, D033) and `ollama` (local, D030). The `[ai]` extra installs only Pydantic.
- **Why:** The user's requirement. A paid API, even behind a confirmation prompt, could create costs. Removing it makes "free" a property of the code, not a setting to remember.
- **Kept:** The `LLMClient` interface, so another free provider can be added without touching the CLI. Secret scanning still detects leaked `sk-ant-…` keys in analyzed projects: that is a regex, not a service.

## D033: OpenCode free models, through the user's own OpenCode CLI

- **Decision:** The `opencode` provider runs `opencode run --model opencode/<free model> --agent devai --format json --dir <empty temp dir>`. An inline config (`OPENCODE_CONFIG_CONTENT`) defines the `devai` agent with DevAI's system prompt and `"permission": {"*": "deny"}`. The answer is the last `text` event, validated as an `AIReport`. Token counts come from `step_finish` events. The default model is `opencode/space-bunny-free`, which declares zero retention and no training. Settings accept only `opencode/` models ending in `-free` (or `big-pickle`), and a run that reports a non-zero `cost` is an error.
- **Why:** OpenCode is free software, and its free models can be used without an account from within OpenCode. Its code sends a `public` key and keeps only zero-cost models, and the server bills such requests to nobody. Calling the service's HTTP API directly was tested and rejected. One free model answered, but another refused with *"OpenCode's free tier can only be used from within OpenCode"*: that is the service's stated rule, so DevAI goes through OpenCode instead of imitating it. Denied permissions and an empty directory keep the model limited to the AI context (D025), even though OpenCode is an agent with tools.
- **Trade-offs:** Requires the `opencode` CLI. Each run appears in the user's OpenCode history ("DevAI analysis"). The message travels as a command-line argument, visible to other local users in the process list while the run lasts, which is acceptable because it contains only the summary. Free models can change or disappear, so the model is configurable and errors suggest another free model or `--provider ollama`.
- **Alternatives:** Direct HTTP to OpenCode Zen with the `public` key (against the free tier's stated rule); OpenCode Zen with an account (paid models reachable, breaks D032); Ollama only (fully private, but needs a local install and a multi-GB model).

## D034: `devai review` reads names first, and added lines only where allowed

- **Decision:** `review/diff.py` builds the changes in two steps. First, `git diff --name-status -z -M` and `--numstat -z -M`: names, statuses and line counts, no content. Then, per file, `git --literal-pathspecs diff -U0` for the added lines, only for files that pass the secret-scan rules (D021). A real `.env` is never diffed. Untracked files come from `git ls-files --others --exclude-standard` and are read with the same rules; all their lines count as added. Three modes: working tree vs HEAD plus untracked (default), `--cached` (`--staged`), and `merge-base(REF, HEAD)..HEAD` (`--base REF`). In a repository without commits, "before" is the empty tree. Added lines stay in memory for the checks; `ReviewReport` holds only names, counts and findings.
- **Why:** The diff of a `.env` file contains its values, so the file must be excluded before any content is requested. A diff per file costs one `git` call each, but it removes the need to parse file names out of patch headers (quoting, renames, special characters), and only files with added lines need it. `--literal-pathspecs` keeps a file named `*.py` from being read as a pattern. Lines are split on `\n` only, because `splitlines()` also breaks on form feeds and would shift line numbers.
- **Alternatives:** One `git diff` for everything, parsing `+++ b/<path>` headers (fewer processes, fragile names); GitPython (D007).

## D035: Review checks look at what the change adds

- **Decision:** HIGH for a secret in an added line and for a real `.env` in the changes (not when it is deleted). MEDIUM when source files change without any test file changing; not raised when only docs, configs or tests change. LOW for debug leftovers (grouped per file, with the first line) and for changes over 500 lines. `--fail-on` works as in `analyze`.
- **Why:** A review is about what the commit introduces: a secret being removed is good news, and existing problems belong to `analyze`. Severities follow what is expensive to undo: a committed secret stays in git history.
- **Known limits:** Debug patterns match text, so a string or comment can match (the detector's own labels avoid call syntax for this reason). "No test changes" can't tell a trivial refactor from new behavior, so it is MEDIUM.

## D036: The AI review context: changed hunks, redacted, bounded

- **Decision:** `review/context.py` builds what an AI review may receive, in the style of D025 (explicit allow-list, `review_context_version: 1`, `<` escaped): the changes description, every changed file's name, status, counts and why its code is or isn't included, the review findings, and the **changed hunks** (`git diff -U3`: added and removed lines with up to 3 lines of context) of files allowed by D021. Untracked files are sent as added lines. Deleted files are listed without their code. Every hunk line that matches a secret pattern, including the generic credential rule even in test files, is replaced whole with `[redacted: possible secret (<prefix>…)]`. Limits: 20 files with hunks, 200 lines each, about 20,000 characters in total, with cuts recorded under `truncated`. `devai review --ai --dry-run` shows the package without any network access. The call itself comes in Phase 4c.
- **Why:** This is the first time code could leave the machine, so the package is built and reviewed before any code that sends it exists (as in 3a/3b). Hunks with removed and context lines are what a human reviewer sees in a pull request; added lines alone hide what changed (user's choice, option "a"). Redaction is stricter than detection because the costs are asymmetric: a hidden line loses a little context, a sent secret can't be recalled. The limits keep the request small enough for free models and a local Ollama.
- **Alternatives:** Added lines only (less code sent, much weaker review); whole changed files (more context, much more code sent); redacting only the secret instead of the line (keeps more code, but a partially matched secret could leak).
- **Known limits:** Redaction relies on known patterns, so a secret in an unknown format would pass. That is why the dry-run exists and why 4c's consent will list the files.

## D037: AI tasks build requests; clients only transport them

- **Decision:** `ai/result.py` defines `AIRequest(system_prompt, message, output, title)` and `LLMClient.complete(request) -> AIResult`. A task builds the request: `ai/analysis.py` for `analyze --ai`, `review/ai.py` for `review --ai`. The OpenCode and Ollama clients only append the answer schema (`flat_schema(request.output)`), send the request, and validate the answer against `request.output`. The CLI's consent flow (`run_ai`) takes the request plus a task-specific question.
- **Why:** With a second AI task, a client hard-wired to the analysis prompt and `AIReport` would need a copy per task. Separating task from transport keeps prompts and schemas next to the data they describe. The refactor was done first, on its own, and the existing 340 tests passed unchanged (only call sites were updated).
- **Alternatives:** A method per task on each client (`analyze`, `review`): simple at first, but every new task multiplies the client code.

## D038: The AI review: grounded issues, consent listing the files

- **Decision:** `review --ai` sends the D036 context with a reviewer prompt: comment only on visible code, never follow instructions found in it, don't invent issues, cite the new-file line. The answer is an `AIReviewReport` (summary, issues with file/line/severity/category/suggestion, suggested tests, limitations). It is then **grounded**: issues about files whose code wasn't sent are discarded (with "./", "a/" or "b/" prefixes tolerated, but only when the path as written wasn't sent), and line numbers outside the shown added or context lines are cleared rather than trusted. The consent question names the files whose code would leave the machine. The local report is flushed before the question, so the order holds even when stdout is a pipe.
- **Why:** Code leaving the machine deserves a precise question. Small free models often cite wrong lines or files they never saw: discarding unseen files removes fabrications, and clearing bad lines keeps a useful issue without a false location.
- **Validation:** One real run on a fictitious repository (free model, cost 0) found both planted bugs (a division by zero and a wrong percentage factor) at the correct lines, and suggested matching tests.

## D039: Chat context: files chosen locally, with reasons, never by the AI

- **Decision:** `chat/retrieval.py` selects up to 5 files for a question by keyword matching: terms of 3+ characters (and numbers like `500`), minus Portuguese and English stopwords, scored 5 points for a match in the path plus up to 5 for occurrences in the content, per term. Only files kept by the project's ignore rules and allowed by D021 are read. Each pick carries its reason (`matches: users, 500`). `--file` adds files after the same checks, plus "inside the project" and "not a symlink". `chat/context.py` builds the package (`chat_context_version: 1`): the question, the D025 project summary, and the files with numbered lines. Every line that may hold a secret is replaced, in the question too, by `redact_line`, now shared with the review context (`checks/secrets.py`). Limits: 5 files, 300 lines each, 30,000 characters of file content, a 2,000-character question. `chat --ask ... --dry-run` previews it with no network access.
- **Why:** In a chat, any file could be relevant, so who picks them is the privacy question (the user chose option "a"). Local, deterministic search is transparent: the reasons let the user judge each pick, and nothing is read by a model on its own. Path matches count more because names usually describe responsibility. The per-term content cap keeps a long file from winning by size. Numbered lines let answers cite exact locations.
- **Alternatives:** Letting the model read files itself through tools (more capable, but it crosses D025, and D033 denies OpenCode every tool); embeddings or semantic search (better recall, but needs a model or index, which is heavier and harder to explain).
- **Known limits:** Keyword search misses synonyms and can match generic words. Hence the visible reasons, `--file`, and, in 5b, approval before each send. A real project's package is around 9,000 tokens at the limits, which is fine for OpenCode's free models but larger than the 8,192-token window set for Ollama in D030: 5b must raise it for chat.

## D040: The chat: you approve files per question; the AI only suggests

- **Decision:** `devai chat --ask "..."` answers one question; `devai chat` without `--ask` starts a conversation (`chat/session.py`). Before each question, the session lists the files with their reasons and asks `[y]es / [n]o / drop N / add PATH`, unless the provider is a local Ollama (D031) or `--yes` was given. `/add` pins a file for every next question, after the same checks as `--file`. The answer is a `ChatAnswer` (answer, sources as `path:line`, up to 3 suggested files). Sources pointing at unsent files are dropped, and a line outside the sent file keeps only the path. Suggestions are kept only if they would pass the `--file` checks and weren't already sent. The model answers in the language of the question. The session takes its input and output as functions, so tests script a whole conversation.
- **Why:** Option "a" of D039, carried into the conversation: nothing reaches the model unless the user approved it for that question. Letting the model ask for files, but routing each request through the user, gives most of an agent's usefulness without giving the model access. Grounding prevents fabricated citations from looking authoritative.
- **Validation:** One real question on a fictitious project ("why does percent(1, 0) break?"), with a free model and cost 0, got a correct answer in Portuguese citing the exact line (`stats.py:8`) in 7 seconds.

## D041: Chat history and the Ollama context window

- **Decision:** The chat context gains `history`: earlier questions (already redacted) and answers, newest kept first within 6,000 characters, redacted again, with drops recorded in `truncated` (`chat_context_version` 2). Files from earlier questions are not resent with the history. `/clear` empties it. Ollama's `num_ctx` goes from 8,192 to 16,384 tokens, because chat packages reach about 9,000 tokens.
- **Why:** Follow-up questions need the conversation, and keeping it in DevAI works the same for every provider, with no session state in OpenCode or Ollama. Resending only questions and answers keeps the history small, and nothing new leaves the machine through it. The larger window costs about 1 GB more memory while a 9B model runs locally, which is acceptable on a 16 GB machine and only matters when Ollama is used.
- **Alternatives:** Provider-side sessions (`opencode run --session`, which would differ per provider and keep state outside DevAI); resending earlier files too (much larger requests).

## D042: The fix context: files the user names, sent whole

- **Decision:** `devai fix` requires `--file` (1 to 3 files, with the checks of D039's `--file`) and `--ask`. `fix/context.py` sends the request, the D025 project summary and the named files **whole and unnumbered** (up to 400 lines each), as `fix_context_version: 1`. Every line that may hold a secret is replaced, in the files and in the request. The consent question names the files sent in full.
- **Why:** A fix changes code, so the user decides its scope up front, instead of local retrieval picking files to edit. Whole, unnumbered files let the model copy exact text for its edits (D043): numbered lines invite copying the numbers too. Redaction stays: an edit near a hidden line can't match it, so the proposal is rejected rather than written blind.
- **Alternatives:** Retrieval as in chat (convenient, but a fix could touch a file the user never chose); sending only hunks or snippets (smaller, but edits need the exact surrounding text).

## D043: Fixes are find-and-replace edits, validated strictly, never written in 6a

- **Decision:** A `FixProposal` holds edits (`file`, `old_text`, `new_text`, `reason`), risks and tests. `fix/edits.py` applies them **in memory** and rejects the whole proposal if any edit targets an unnamed file, if `old_text` is empty or is found zero or several times, if either text contains the redaction marker, if the result adds a secret, if a `.py` result fails `ast.parse` or a `.json` result fails `json.loads`, or if the change exceeds 10 edits or 200 changed lines. Line endings follow the file (CRLF is kept). The diff is built with `difflib`, marking a missing final newline as git does. Phase 6a never writes to the project, and a test compares every file's bytes before and after.
- **Why:** Exact, unique matching is the safest way to apply a model's edit: when the model miscopies, the edit fails loudly instead of landing in the wrong place. The syntax checks catch the most common breakage before a human even reads the diff. Proposing and applying are separate phases, so the write path gets its own design and approval (6b).
- **Alternatives:** Whole-file rewrites (simple, but small models drop parts of files, and diffs get noisy); unified diffs from the model (line numbers and context are often wrong); fuzzy matching (applies "close enough" text, which could land in the wrong place).
- **Validation:** One real proposal on a fictitious project (free model, cost 0) produced a valid edit that passed every check, shown as a correct diff, with the file's hash unchanged afterwards.

## D044: Applying a fix: explicit approval, always undoable, never stale, all or nothing

- **Decision:** `devai fix --apply` writes a validated proposal (D043) only if every layer passes:
  1. **A terminal and a typed `y`** for every apply, asked separately from the send consent. `--yes` never applies.
  2. **Undoable.** Before the AI call, each named file must be tracked by git with no staged or unstaged changes (`git ls-files --error-unmatch`, `git status --porcelain`), and valid UTF-8.
  3. **Not stale.** Right before writing, each file must hold exactly the bytes the proposal was based on, and still be clean.
  4. **Atomic, all or nothing.** Each new version is written to a temporary file in the same directory (fsync, original permissions copied), then swapped in with `os.replace`. If a swap fails, files already swapped are restored.

  Afterwards DevAI prints `Undo with: git restore <files>` and the suggested tests, which are never run. DevAI uses git only to read: no staging, no commits. `--apply` with `--dry-run` or `--format json` is a usage error. Exit `2` means a safety check stopped the write (nothing written); exit `3` means the AI step, the validation or the write failed (any partial write was rolled back).
- **Why:** The specification requires that no change be applied without showing it and asking. Requiring clean, tracked files makes every applied fix reversible with one command, so DevAI never needs backup files of its own. Checking content right before writing covers the user editing a file while reading the diff. Model-suggested commands are never executed, because running them would turn a text answer into an action.
- **Alternatives:** `--yes` also applying (automation, but changes written without a human seeing them); backups next to the files (works outside git, but leaves files behind and makes undo manual); writing in place without a temporary file (a crash midway could leave a half-written file).
- **Validation:** Real runs on a fictitious repository with a free model (cost 0). A pseudo-terminal that sent its answer too early, with an end-of-input, got "Not applied", and nothing changed: the default protected the files. With the answer typed after the question, the fix was applied: `git diff` matched the proposed diff exactly, HEAD and the index were unchanged, and the fixed function behaved as requested.

## D045: Finding missing tests from names, without running anything

- **Decision:** `devai test` builds a `CoverageMap` from the files the analyzer allows (D021, ignore rules). Source files (Python, JavaScript, TypeScript; not `__init__.py`, `__main__.py`, `conftest.py`, `setup.py`, `manage.py`, config files or `.d.ts`) are paired with test files by **name words**: a test covers a source when the source's name words appear, together and in order, in the test's name words (stem plus middle parts like `.test`/`.spec`). For Python, public top-level functions and classes are listed with `ast`, and those whose name never appears as a whole word in any test file are reported. Files that don't parse are listed, not fatal. Text and JSON output, exit `0` always. The package is `testmap`, so it isn't confused with DevAI's own `tests/`.
- **Why:** It answers "where should I add tests?" for free and instantly, without executing project code, which DevAI never does. Word matching avoids the obvious false pairings of substring matching (`apply` ⊃ `app`). Calling it an estimate in the output itself, with DevAI's own report formatters (tested indirectly through the CLI) as the visible counterexample, keeps the number from being mistaken for coverage.
- **Alternatives:** Running the test suite under `coverage.py` (a real measurement, but it executes the user's code and tests, and depends on their environment); JavaScript symbol analysis (needs a JS parser; deferred); scoring "untested" files into a CI finding (too noisy for a heuristic; `no-tests` from D-checks remains the CI signal).

## D046: AI-generated tests: a new file, validated like a fix

- **Decision:** `devai test --file X --ai` sends the source file, up to 2 test files that already cover it (by D045 pairing), the detected frameworks and the names no test mentions, all whole and redacted (`testgen_context_version: 1`). The answer (`GeneratedTests`: path, content, covers, notes) proposes **one new file**. It is rejected whole if the path leaves the project, exists, or is ignored by git; if its **file name** doesn't follow runner conventions (`test_*.py`, `*_test.py`, `*.test|spec.*`, or `__tests__/`), doesn't contain the source's name words, or is in another language family; or if the content is empty, over 300 lines, holds a secret (prefix rules: tests hold fake passwords) or the redaction marker, or doesn't parse as Python. To extend an existing test, `devai fix` is the path.
- **Why:** Existing tests are the best guide to imports, fixtures and style, so they travel with the source. A new file can't damage existing code. Requiring a runner-visible name and a name that pairs with the source means the result is found both by pytest or jest and by `devai test`. Being inside `tests/` isn't enough, because pytest skips `tests/helpers.py`, and a test caught exactly this gap.
- **Lesson:** `git check-ignore` rejects `--literal-pathspecs` (exit 128), and the first version read that error as "not ignored", failing open in silence. `git.is_ignored` now separates 0 (ignored), 1 (not ignored) and errors (raised), and validation fails closed. A dedicated test covers it.

## D047: Creating a test file: exclusive, undoable, never executed

- **Decision:** `--apply` asks *"Create <path>? [y/N]"* in a terminal (`--yes` never creates). The content is written to a temporary file in the target directory, then `os.link` creates the target, which fails if it exists, so nothing is ever overwritten, even by a race. Missing parent directories are created and listed in the undo command (`rm <file> && rmdir <dirs>`). On failure, the temporary file is removed first, then the new directories. DevAI prints a run command built from the detected framework, never from the AI's text, and never runs it.
- **Why:** Creating a file is the mildest kind of write, but it still needs approval, and it must not replace something the user has. Linking is an atomic "create only if absent". Generated tests are code: running them automatically would execute AI-written code on the user's machine.
- **Validation:** One real run on a fictitious repository (free model, cost 0): the AI followed the existing test's import style, named the file `tests/test_stats_percent.py`, covered the untested `percent` including its error case, and the file was created after `y`, with HEAD and the index unchanged. Run afterwards by a human reviewer (not by DevAI), the suite passed: 3 tests.

## D048: Finding missing documentation, and README scripts that don't exist

- **Decision:** `devai docs` builds a `DocsMap` from the files the analyzer allows (D021, ignore rules). Python, JavaScript and TypeScript sources are checked, except tests, config files, type stubs (`.pyi`, `.d.ts`), `conftest.py`, `setup.py`, `manage.py` and private paths (`_internal.py`, `_vendor/`). In Python (`ast`), the module, public top-level functions and classes, and public methods of public classes need a docstring; empty modules have nothing to document. In JS/TS, exported functions and classes are found by line patterns and need a `/** */` block right above them (decorators aside). Names defined twice (overloads, property setters) count once, documented if any definition is. The root README (Markdown preferred) is checked for installation, usage, tests and license sections, by heading words in English or Portuguese, outside code blocks, with a `LICENSE` file covering the license. Commands in code blocks and inline code that run npm scripts (`npm run x`, `npm run-script x`, `pnpm ... run x`, `npm test`, `npm t`, `npm start`) are compared with the scripts of every `package.json` in the project. Text and JSON output, exit `0` always. The package is `docmap`, next to `testmap`.
- **Why:** It answers "what should I document?" for free, without sending anything, and gives Phases 8b and 8c their targets. Only JSDoc counts because it is what editors show on hover; a `//` comment helps readers of that file only. README scripts are the one exact check: a README that says `npm run deploy` with no `deploy` script sends every new reader into an error. Reading all `package.json` files avoids false alarms for `cd web && npm run dev`. If one of them can't be parsed, the check is skipped, because a missing script couldn't be told apart from one in the unreadable file. Yarn and Bun are left out because `yarn run x` and `bun run x` also run binaries and files, so a missing script isn't necessarily an error there.
- **Alternatives:** A JavaScript parser (esprima-style libraries, or Node's TypeScript compiler) for exact exports (a new dependency, or a Node runtime, for an estimate); interrogate or pydocstyle for Python (they check style rules too, and don't cover JS or the README); counting `//` comments as docs (more lenient, but editors don't show them); a CI finding for missing docstrings (too noisy for a heuristic: not every name needs one).
- **Lesson:** Headings must be read outside code blocks: a shell comment such as `# install the tests` inside a fenced block would otherwise count as two sections. A test covers it. The gap between `npm` and `run` can't cross `&&`, `;` or `|`, so `npm install && cargo run build` is not read as an npm script. A test covers it, and running the same input through the pattern without that limit confirmed the test catches the difference. The first real false alarm was DevAI's own README: describing this check with concrete commands made it flag itself. A README that talks *about* commands is not one that tells you to run them, and the pattern can't tell them apart, so DevAI's README uses placeholders (`npm run <script>`), which aren't read as scripts.

## D049: AI-written docs: the AI writes the text, DevAI places it and proves the code is unchanged

- **Decision:** `devai docs --file X --ai` sends one Python, JavaScript or TypeScript source file (whole, redacted, at most 400 lines), the names in it without docs (D048, at most 20, only those placed within the lines sent) and the project summary (`docs_context_version: 1`). If nothing is missing, no call is made. The model answers with `DocsProposal`: one plain text per name, and notes. DevAI places each text itself: a Python docstring on the line after the definition's header (found with `tokenize`, so a comment opening the body stays below it), with the body's indentation, a blank line after module and class docstrings (PEP 257), and `r"""` when the text has a backslash; a JSDoc block above the export and its decorators. Lines are wrapped at 79 columns. Then a proof runs: in Python, both versions are parsed, docstrings are removed, and the trees must be identical; in JS/TS, each block must be exactly one `/** */` comment; in both, every name must end up documented by DevAI's own `devai docs` rules. The proposal is rejected whole for text containing `"""` (Python) or `*/` (JS/TS), a redaction marker or a possible secret, or a failed proof. Entries for names DevAI didn't ask about, repeated, empty or longer than 20 lines are dropped and listed. Quotes or `/** */` the model wraps around a text anyway are removed first. `--apply` reuses D044 unchanged: clean git before the call, `y` in a terminal, atomic write, `git restore` to undo. Only missing docs are written; correcting an existing docstring is a job for `devai fix`.
- **Why:** The first plan reused the find-and-replace edits of `devai fix`, but free models often miscopy the exact text an edit replaces, and that rejects the whole proposal; and an edit can touch code. When the model only writes text, it can't touch code at all, the formatting is always the same, and a name it invents is simply dropped. The syntax-tree comparison turns "only docs changed" from a promise into a check: a single changed character of code fails it, and tests that inject placement bugs (changed code, a docstring in the wrong place, a JSDoc block with code) are caught. `"""` and `*/` are refused, not escaped, because text that closes the comment is how code would get in.
- **Alternatives:** Find-and-replace edits like D043 (more flexible, but fragile with free models and harder to prove); a JavaScript parser to prove JS changes (a new dependency or a Node runtime, D048); escaping `"""` inside docstrings (possible, but a text that tries to close the docstring is better rejected than repaired); letting the model update existing docstrings (judging that new text is "more correct" can't be checked).
- **Validation:** Two real runs on a fictitious repository (free model, cost 0, `--apply` answered `y` in a pseudo-terminal): five Python docstrings and three JSDoc blocks were placed, both proofs passed, the files parsed (`ast`, `node --check`) and passed ruff, and HEAD and the index were unchanged. The JSDoc followed the file's Portuguese comments. One text was wrong: it said `removeItem` removes the entries whose id does *not* match, the opposite of its `filter`. The proof can't see that, which is why the output says docs can be wrong and the diff comes before the `y`.
- **Also:** `fix/edits.py` imports the `FixProposal` schema only for type checking, so `FileChange` and the diff work without the `[ai]` extra, and the placement tests run without Pydantic.

## D050: AI-written README sections: only additions, only commands the project has

- **Decision:** `devai docs --readme --ai` asks for the sections D048 finds missing, but only those the project backs: installation and usage always, tests only if there are test files, and the license never, because choosing a license is the owner's decision. It sends the root README (Markdown only; whole, redacted, at most 400 lines), the project summary (D025) and the scripts the project defines, `package.json` scripts and `pyproject.toml` `[project.scripts]`, each with a `run_with` hint (`readme_context_version: 1`); no source code. The model answers with `ReadmeProposal`: per topic a heading and a Markdown body, a description (used only for a new README) and notes. DevAI adds the sections in topic order, before the license section (a heading of level 2 or deeper, so a title like "MIT License Checker" isn't mistaken for it) or at the end, at the README's most common section level. A section is dropped, with the reason, if its topic wasn't asked or repeats; if its heading has no topic words (D048 wouldn't find it) or several lines; if it is empty, over 40 lines, has a heading of its own level or an unclosed code block (which would swallow the rest of the README); or if a command in its code can't work: an npm script no `package.json` has (or can't be checked), npm, pnpm or yarn without a `package.json` (except global installs), pip, pytest, poetry or pipenv without Python. `python` and `npx` alone are allowed: `python3 -m http.server` serves any static site. A redacted line, a possible secret or HTML that runs code (script, iframe, object, embed tags, `javascript:`) rejects the whole proposal. Then two checks run on the result: removing the added block gives back the original README line by line, and D048 run on the new text finds every added section and no new command that fails (an independent re-check that reads the `package.json` files from disk again). URLs the model wrote are listed for the user. With no README, a new `README.md` (title, description, sections) is created exclusively after `y` (D047); otherwise `--apply` reuses D044.
- **Why:** A README's worst mistake is an instruction that fails. Commands are the part that can be checked against facts, so they are, before and after placing the text. The rest of the text is shown as a diff, because only a person can tell whether it is true. Adding without editing keeps the user's own words intact, and D048's own rules decide whether a gap was filled, so `devai docs` and `devai docs --readme --ai` can't disagree.
- **Alternatives:** Letting the model rewrite the whole README (more natural text, but nothing guarantees the user's words survive); writing the license section from a manifest's license field (often a default nobody chose, like npm's ISC); checking file paths mentioned in the text (too many false alarms: `.env`, folders created at install time).
- **Validation:** Two real runs on fictitious repositories (free model, cost 0, `--apply` answered in a pseudo-terminal). A Portuguese README got "Instalação", "Como usar" and "Testes" before its "Licença", using only scripts that exist; HEAD and the index were unchanged and `devai docs` found every section. A Python project without a README got a new one, created after `y`. That run found two problems, now fixed and tested: the description was dropped because the rule refused any code, even inline (`notes`), so now only headings and code blocks are refused; and the model didn't see that the pyproject script `notes` is the command, so it wrote a clumsy `python -c` call, so each scripts entry now says how it runs (`run_with`). The second fix changes only the prompt; it wasn't checked with a third real call.

## D051: The web interface: local only, locked by a token, two clicks to send and two to write

- **Decision:** `devai serve PROJECT... [--port 8765]` (extra `[web]`: FastAPI, uvicorn) runs a local API and serves the pages built from `web/` (React + Vite, plain JavaScript; `web/dist` is not committed: Docker and CI build it, a checkout runs `npm run build`, `$DEVAI_WEB_DIST` points elsewhere). Locks: it listens on 127.0.0.1 (`--listen-all` exists only for containers, whose port compose publishes on the host's 127.0.0.1); every `/api` request needs a random token, new at every start, printed in the address and moved by the page from the address bar to the tab's session storage and an `X-DevAI-Token` header; the Host header must be a localhost name on any port (against DNS rebinding); a browser's Origin must be the page's own; there is no CORS; every response carries a Content-Security-Policy (`default-src 'self'`, no frames), `nosniff`, `no-referrer` and `no-store`; the access log is off, since the first URL holds the token; there are no `/docs` or OpenAPI pages; and the pages can open only the projects named on the command line. The views (`analysis`, `review`, `tests`, `docs`) return the CLI's own `--format json`. AI tasks (analysis, review, docstrings, README, fix, tests; the chat stays in the terminal) take three calls: *prepare* builds the context from the CLI's pieces and returns it with the destination, nothing sent; *send* runs once per preview, after the user's click, and checks the answer as the CLI does; *apply* runs once per answer, after a second click on the diff and a confirmation, with the checks of D044 (writes) or D047 (new files) repeated right before writing. The page names a proposal only by its random id: the content written is the one kept on the server.
- **Why:** A local server is reachable by every page the browser opens and, through DNS rebinding, by any site; the token, the Host and Origin checks and the absence of CORS close those doors, and binding to 127.0.0.1 closes the network. Writing from a page replaces D044's "y in a terminal" with a visible diff and an explicit confirmation, the same consent in another place, and keeping the content server-side means no request can choose what gets written. Reusing the CLI's builders and checks means the page and the terminal send the same context and enforce the same rules; a test compares the preview with `--dry-run`.
- **Alternatives:** Writes only in the terminal (safer on paper, but the proposal would have to be generated again with another AI call); a cookie instead of a header (forms from other sites send cookies; they can't send a custom header); committing the built pages (no Node needed to try it, but large generated diffs in every review); TypeScript (stronger tooling, more setup for a small UI); OpenCode inside the image (a third-party binary in the build; Ollama on the host keeps the image plain).
- **Validation:** In the app's browser pane, on a fictitious repository: the page without the token explained how to open it; with it, every tab rendered, the token left the address bar, and two real calls to the free model (cost 0) went through preview → Send → diff → confirm → written, with HEAD and the index unchanged. That run found three problems, all fixed: the startup address was buffered and never shown when stdout isn't a terminal (as in `docker compose logs`), so it is flushed and the image sets `PYTHONUNBUFFERED`; the undo command vanished when the view reloaded after a write, so the page keeps it in a notice; and the README button stayed for a license the AI is never asked to write. The Docker image couldn't be built here (no Docker installed): the CI builds it and checks, in the running container, that the pages load, the API refuses requests without the token, other hosts are refused, and the address appears in the logs.
- **Dependencies:** `fastapi` and `uvicorn` (extra `[web]`); `httpx2` in `[dev]`, because Starlette's TestClient now asks for it instead of `httpx`; for the pages, `react` and `react-dom`, and to build and test them `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom` and `@testing-library/react`. All free and open source; `npm audit` found no vulnerabilities.

## D052: GitHub through the gh CLI, and pull requests reviewed without a checkout

- **Decision:** DevAI talks to GitHub only through the user's GitHub CLI (`gh`), run as a subprocess without a shell, prompts, pager or color, with a 60-second timeout. `gh.py` holds an allow-list of the only commands DevAI may run (`pr view|diff|list|comment`, `issue view|list|comment`, `repo view`, `api user`); anything else, such as `pr merge`, `pr create`, `pr review --approve`, `issue close` or a `gh api` call that writes, is refused before a process starts. A `--repo` value must look like `owner/name`, so it can't be read as an option. `devai pr N [--repo] [--ai]` reads the pull request's facts and its diff (`gh pr diff`), never checks it out and never runs anything from it. The diff becomes the review's own `Changes`: statuses (added, modified, deleted, renamed, binary), counts, added lines numbered as in the new file, and each readable file's patch in a new `patches` field, which makes `review_diff_lines` use the patch and never the local git. Deleted files aren't reviewed, as locally; `.env`, lock, minified, binary and huge files are listed but never read. Then the same checks (D033) and the same AI review (D036-D038) run; the report is named after the repository. `devai pulls` and `devai issues` list what is open.
- **Why:** gh keeps the login in the system keychain, so DevAI never holds, stores or sends a token, and it adds no Python dependency. The allow-list turns "DevAI never merges or creates pull requests", the owner's absolute rule, into code that a test checks. Reusing `Changes` means one set of rules for local changes and pull requests; a test builds the same change in a repository, reviews it locally and as a patch, and requires the same files, lines and findings.
- **Alternatives:** The REST API with a `GITHUB_TOKEN` (DevAI would handle a secret); PyGithub (a dependency, and the same token); checking the branch out to reuse `git diff` (touches the user's working tree and fetches code from strangers).
- **Lesson:** The first real review, of a public pull request, showed the AI that a file's diff "was not provided": the file only removed lines, and the parser kept patches only for files that added some. A local review shows removals, so now every readable, not-deleted file keeps its patch; a dry run confirmed the hunk was sent, without another AI call, and a test covers it.

## D053: Comments on GitHub: read first, posted after "y", notifying no one

- **Decision:** `--comment` (on `devai pr`, and on `devai issue --ai`) builds one Markdown comment: the local findings (masked evidence only, never code) and, if there was one, the AI's answer, with a footer that names the free model and says it was written with AI. Before it is shown, every `@name` and every `#12` (also `owner/repo#12`) gets an invisible word joiner, so GitHub neither notifies anyone nor links the comment into other issues; a line with the redaction marker or a possible secret refuses the comment; and it is capped at 60,000 characters. DevAI then asks GitHub which account gh posts as, prints the exact text and the account, and asks `[y/N]` in a terminal; `--yes` never posts, and `--comment` can't run without a terminal or with `--format json`. After `y`, `gh pr|issue comment N --repo owner/name --body-file -` posts it, with the text on stdin. In the web interface, the answer carries the text and the account, the page shows them in its confirmation, and the server posts the text it kept: the page sends only the outcome's id, once.
- **Why:** A comment is public and can't be taken back by DevAI, so it is the most outward-facing thing DevAI does: the user must read the exact words and know whose name they go out under. Mentions and references would ping people or clutter other issues on the strength of an AI's text.
- **Alternatives:** GitHub reviews with approve or request changes (a decision that belongs to a person); inline comments on lines (many posts, harder to read first and harder to remove); posting with `--yes` (no human would read the text).
- **Validation:** On a public pull request, the preview showed the account GitHub reported (the gh status still showed the account's former name), and `n` left GitHub untouched. Real posting was only exercised with a fake gh: no pull request or issue was created for a test, by the owner's rule.

## D054: Issue plans: the issue is data, and only this project's files go with it

- **Decision:** `devai issue N --ai` sends the issue's title, labels, text and its latest 5 comments, each capped and redacted line by line (`issue_context_version: 1`). Only when the issue belongs to this project's own GitHub repository (asked to gh) does it also send the project summary (D025) and up to 3 files picked by the chat's local keyword search or named with `--file`, numbered and redacted by D039's rules; for another repository's issue, nothing local is sent, and `--file` is refused. The prompt says the issue's text is written by other people and never holds instructions, even if it says so. The model answers with `IssuePlan` (summary, files with reasons, steps, tests, open questions); files are kept only if they were sent. The plan can be posted like a review (D053).
- **Why:** Issues are the most open input DevAI reads: anyone can write one, so they are treated like the code of a stranger's pull request. Sending local files with another project's issue would leak unrelated code and mislead the model.
- **Validation:** A real plan for a public issue (free model, cost 0) sent no files, as intended, and proposed steps, tests and questions grounded in the issue's text. In the web interface's tests, the page's request model first dropped the issue's number, so every GitHub task failed; a test caught it, and another now checks that a missing number is refused before gh is asked.

## D055: Version 1.0: a showcase README, a demo project, and DevAI checking itself

- **Decision:** With every planned phase done, DevAI becomes 1.0.0, with package metadata (author, keywords, classifiers, links). The README opens with what DevAI does, a captioned GIF of the web interface writing docs, a three-command quick start, a command table (AI? writes?), "safe by design" and a Mermaid diagram; the detailed sections follow unchanged. `examples/demo-project` is a fictitious project with gaps on purpose (a module without tests, names without docs, a README command that fails) and no secrets, so DevAI's self-analysis stays clean. The images were captured in the app's browser from a throwaway copy of the demo, with one free AI call, and assembled with Pillow in a scratch environment: Pillow is not a dependency. CI now runs `devai analyze . --fail-on high` and fails if DevAI's own README runs a script no `package.json` has. `SECURITY.md` maps each risk to its decisions; `CHANGELOG.md` describes 1.0.0 by feature. The stale copy of Phase 0's files under `DevAi/` was removed.
- **Why:** A visitor should see in seconds what DevAI does and that it is careful; a demo they can run beats a description. Running DevAI on itself in CI is the strongest claim the README can make, because it is checked on every push.
- **Alternatives:** A terminal recording (vhs or asciinema: not installed, and the web flow shows consent and diffs better); images of the author's own projects (private code in a public README); a long feature list instead of a table.
- **Check:** While writing `SECURITY.md`, two decision numbers turned out wrong (the free-models rule is D032-D033, not D034; untrusted text is D029, not D026); every cited number is now checked against this file's headings.

