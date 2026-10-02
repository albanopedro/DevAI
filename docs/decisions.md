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
