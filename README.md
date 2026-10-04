# DevAI

[![CI](https://github.com/albanopedro/DevAI/actions/workflows/ci.yml/badge.svg)](https://github.com/albanopedro/DevAI/actions/workflows/ci.yml)

AI-powered developer assistant for code analysis, review, testing and software engineering automation.

> **Status:** early development (Phase 8: documentation, complete).

## Goal

DevAI analyzes a software project: it maps the structure, languages, frameworks, dependencies, tests and configuration, flags likely problems, and uses AI to interpret what it found.

It is a learning and portfolio project, and it grows in small, tested phases.

## Principles

- **100% free, always.** DevAI uses no paid service, no paid API and no account of any kind. Its AI features use only free models: OpenCode's free models through your own OpenCode, or local models through Ollama. A model that could cost money is refused before anything runs.
- **Deterministic first, AI second.** `devai analyze` works offline with no API key. AI is opt-in and only receives a structured, reviewable context.
- **Privacy by default.** Honors `.gitignore`, never reads `.env` files, never prints secrets, and never sends code to an external API without explicit consent.
- **User in control.** DevAI never applies code changes without showing a diff and asking for approval, and never commits or pushes.

## Installation

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"        # DevAI + test tools (only dependency: pathspec)
pip install -e ".[dev,ai]"     # also the free AI analysis (adds Pydantic)
```

## Usage

```bash
devai --help
devai --version
devai analyze                     # current directory
devai analyze path/to/project
devai analyze --format json       # machine-readable output
devai analyze --fail-on high      # exit code 1 if there is a HIGH finding (for CI)
devai analyze --ai --dry-run      # preview what an AI analysis would send (sends nothing)
devai analyze --ai                # free AI analysis (OpenCode free model), after asking
```

Example output:

```
DEVAI ANALYSIS
────────────────────────────────────
Project:        campo-main
Path:           /home/user/code/campo-main
Files:          59 (filesystem + .gitignore)
Git repository: no
README:         yes

Languages:
  CSS         11 files   50%
  JavaScript  10 files   45%
  HTML         1 file     5%

Frameworks:
  Bootstrap, React, Vite

Dependencies:
  package.json  5 runtime, 9 dev

Tests:
  none detected

Configuration:
  .gitignore
  eslint.config.js
  vercel.json
  vite.config.js

Structure:
  public/   3 files
  src/     47 files
  (root)    9 files

Findings:
  ⚠ MEDIUM  No automated tests detected

Passed:
  ✓ README found
  ✓ .gitignore found
  ✓ No exposed .env files
  ✓ No known secret patterns found

Secrets scan: 30 files scanned, 29 skipped
```

### How files are found

DevAI describes the project from file **names**, `.gitignore` and dependency manifests. Only the secret scan reads other files, under the rules in [Findings](#findings).

- **Inside a git repository** (or any subdirectory of one), git lists the files: tracked files plus untracked files that aren't ignored. Every ignore rule applies, including nested `.gitignore` files, `.git/info/exclude` and your global excludes file. Shown as `(git)`.
- **Otherwise**, DevAI walks the directory, skips common generated folders (`node_modules`, `.venv`, `__pycache__`, `dist`, `build`...) and applies the **root** `.gitignore` if there is one. Shown as `(filesystem)` or `(filesystem + .gitignore)`. Limitation: `.gitignore` files in subdirectories are not read in this mode.

### What is detected

| Section | How | Files opened |
|---|---|---|
| Languages | file extension (JSON, YAML, Markdown are not languages) | none |
| Dependencies | `package.json`, `pyproject.toml` (`[project]`, optional deps, dependency groups), `requirements*.txt`, in any folder. `go.mod`, `Cargo.toml`, `pom.xml`, `Gemfile`, `composer.json` are detected but not parsed | manifests only |
| Frameworks | known dependency names (React, Vite, Express, Django, FastAPI...) | none |
| Tests | test files by convention (`test_*.py`, `*.test.js`, `tests/`...) and test frameworks in the dependencies | none |
| Configuration | well-known config files by name (`Dockerfile`, `tsconfig.json`, `.env*`, CI workflows...) | none; `.env` is listed but never read |

A manifest that can't be parsed shows up as a warning. The warning never includes file contents.

### Findings

After describing the project, DevAI runs checks and reports problems by severity:

| Severity | Rule | What it means |
|---|---|---|
| HIGH | `secret/*` | A known secret format in a file: AWS, GitHub, OpenAI, Anthropic, Google, Slack, Stripe keys, private keys |
| HIGH | `env-not-ignored` | A real `.env` file is tracked, or isn't ignored by git |
| MEDIUM | `secret/generic` | A quoted value assigned to a name like `api_key`, `token` or `password` (placeholders filtered; skipped in test files) |
| MEDIUM | `no-tests` | Source code, but no test files |
| LOW | `no-readme`, `no-gitignore` | Missing README or `.gitignore` |

**Privacy rules of the secret scan:**

- Real `.env` files (`.env`, `.env.local`, `.envrc`...) are **never opened**. Templates (`.env.example`, `.env.sample`...) are scanned, since they are meant to be committed.
- Symlinks, lock files, minified files, binaries and files over 1 MB are skipped.
- A finding shows only the public prefix of a secret (`AKIA…`, `ghp_…`), the same for everyone. It never shows the secret or the line it is on, in text or JSON.
- Contents are checked in memory and discarded. Nothing leaves your machine.

No set of patterns catches every secret. The report says "No known secret patterns found", not "no secrets".

### JSON output and exit codes

`--format json` prints everything in the text report as JSON, including the file list and each finding. The top-level `schema_version` (currently `1`) changes only when the structure changes incompatibly.

| Exit code | Meaning |
|---|---|
| `0` | Success (findings don't fail the run unless you use `--fail-on`) |
| `1` | A finding at or above the `--fail-on` level (`high`, `medium`, `low`) |
| `2` | Usage error: no command, path is not a directory, invalid argument, AI setup problem |
| `3` | The AI analysis failed (network, API key...). The deterministic report was still printed |

Example CI step:

```bash
devai analyze --fail-on high
```

### Reviewing changes before a commit

`devai review` checks your current git changes: locally, without AI, and for free.

```bash
devai review                          # working tree vs HEAD (staged, unstaged, untracked)
devai review --staged                 # exactly what the next commit would contain
devai review --base main              # committed changes since the branch left main
devai review --staged --fail-on high  # e.g. as a pre-commit check (exit 1 on HIGH)
devai review --ai                     # plus a free AI review of the changed code
```

| Severity | Rule | What it means |
|---|---|---|
| HIGH | `secret/*` | A known secret format in an **added** line (a secret in a removed line is on its way out) |
| HIGH | `review/env-file` | A real `.env` file is added or changed, so its values would be committed |
| MEDIUM | `review/no-test-changes` | Source code changed, but no test file did (not raised for docs/config-only changes) |
| LOW | `review/debug-statement` | `console.log`, `debugger`, `breakpoint()` or `pdb` added (one finding per file) |
| LOW | `review/large-change` | More than 500 lines changed: consider splitting the change |

How it reads your changes:

- **Names first, content second.** DevAI asks git for the list of changed files (names, statuses, line counts), then reads the added lines only of files the privacy rules allow. A real `.env` is never read, not even through its diff. Lock, minified, binary, symlinked and large files are skipped, as in the secret scan.
- **Untracked files count as added**, so a new `.env` or a new file with a secret shows up before `git add`.
- **The report never contains your code**: only file names, line counts and findings, in text and JSON.
- `--format json` and `--fail-on` work as in `analyze`. Outside a git repository, or with an unknown `--base`, the exit code is `2`.

#### AI review

`devai review --ai` adds a free AI review of the changed code: what the change does, issues with file, line, severity, category and a suggested fix, tests the change should have, and what the AI couldn't judge. It uses the same free providers as `analyze --ai` (OpenCode's free models by default, or a local Ollama) and the same options (`--dry-run`, `--yes`, `--provider`, `--format json`).

```bash
devai review --ai --dry-run   # 1. see exactly which code would be sent
devai review --ai             # 2. send it, after confirming the list of files
```

- **You see the list of files first.** DevAI prints the local review, then asks: *"Send the changed code of 2 files (~1,200 tokens) to OpenCode (…, free model)? Files: src/app.py, tests/test_app.py."* Local Ollama runs without asking. If no code can be sent (for example, only a `.env` changed), the AI step is skipped.
- **Issues are checked against what the AI saw.** An issue about a file whose code wasn't sent is discarded, and a line number outside the shown hunks is cleared. The report says how many issues were discarded.
- **Never affects `--fail-on`**, and if the AI step fails you still get the local review, with exit code `3`.

What would be sent:

| Sent | Never sent |
|---|---|
| Which changes (working tree, staged, or since a base) | Whole files, or files that didn't change |
| Changed file names, statuses and line counts | A real `.env`, lock, minified, binary, symlinked or large file |
| The review findings (masked evidence) | Secrets: every line matching a secret pattern is replaced, whole, with `[redacted: possible secret (AKIA…)]` |
| **Changed hunks** of allowed files: added and removed lines, with up to 3 lines of context | Absolute paths, deleted files' code |

- Redaction covers added, removed **and** context lines, and applies the broad credential rule even in test files: hiding a line costs little, sending a secret can't be undone.
- Limits: 20 files with hunks, 200 lines per file, about 20,000 characters in total. Every changed file stays listed with the reason its code isn't included (`deleted`, `not read (privacy or size rules)`, `not included (size limit)`), and cuts are recorded under `truncated`.
- Code comes from the reviewed project and is untrusted: a comment saying "ignore your instructions" is data. `<` is escaped, so nothing in the code can close the prompt's delimiter.

### Asking about a project (chat)

`devai chat` answers questions about a project, citing `path:line`, with free models (the same providers as `analyze --ai`). You approve the files before each question.

```bash
devai chat                                              # a conversation in the terminal
devai chat --ask "why does /users return 500?"          # one question, then exit
devai chat --ask "how is the cart saved?" --file src/cart.js   # add a file yourself
devai chat --ask "why does /users return 500?" --dry-run       # see what would be sent
```

In a conversation, before each question DevAI lists the files and why they were picked, then asks `[y]es / [n]o / drop N / add PATH`. Commands: `/add PATH` sends a file with every next question, `/drop PATH`, `/files`, `/clear` (forget the conversation), `/help` and `/quit` (Ctrl+D also works).

How it works:

- **Files are picked locally, with a reason.** The question's terms (stopwords removed, in Portuguese and English) are matched against each file's path (worth more) and content (capped). The best 5 are shown with what they matched, e.g. `api/users.py  matches: users, get, 500`. No AI decides what to read.
- **`--file` gets the same checks** as everything else: it must be inside the project, not a symlink, not ignored by `.gitignore`, and not an environment, lock, minified, binary or large file.
- **What would be sent:** the question, the project summary (as in "What is sent" above), and the chosen files with **numbered lines**, so an answer can cite `path:line`. Every line that may hold a secret is replaced, in the files and in the question. Limits: 5 files, 300 lines each, about 30,000 characters of file content.
- **The AI never reads a file by itself.** It can *suggest* up to 3 files it would need. Suggestions are shown only for project files that would pass the `--file` checks, and you decide whether to send them (`--file` or `/add`).
- **Answers are checked against what was sent.** Sources that point at files that weren't sent are dropped, and a line number outside a sent file keeps only the file. The answer says how many sources and suggestions were dropped.
- **The conversation is remembered locally.** Each question also sends the earlier questions and answers (the most recent ones that fit about 6,000 characters), so a follow-up like "and the POST route?" makes sense. Files from earlier questions are **not** resent unless they are picked or added again. `/clear` forgets the conversation.
- **Consent as everywhere else:** OpenCode's free models get the question only after your `y`, a local Ollama doesn't ask, and `--yes` skips the question. Outside a terminal, use `--ask` with `--yes`. If the AI step fails, `--ask` exits with code `3`; in a conversation you can simply ask again.

### Finding missing tests

`devai test` estimates where tests are missing, locally and for free. It runs nothing: no tests, no project code.

```bash
devai test                 # text report
devai test --format json   # for scripts
```

- **Source files without a matching test file**, by name: `report.py` is covered by `test_report.py` or `report_test.py`, `Cart.jsx` by `Cart.test.jsx`, `Cart.spec.jsx` or `__tests__/Cart.jsx`. Names are compared as words, so `test_apply.py` doesn't cover `app.py`. Python, JavaScript and TypeScript are checked; `__init__.py`, `conftest.py`, config files and type declarations are not.
- **Python names no test mentions:** public top-level functions and classes (parsed with `ast`) whose name never appears in any test file.
- **It's an estimate, and it says so.** Code tested indirectly, through other functions or the CLI, looks untested here. DevAI's own report shows this: its report formatters are tested through the CLI output, and they still appear in the list. Use it to choose where to look, not as a coverage number. (For real coverage, use a tool like `coverage.py` that runs your tests.)
- Always exits `0`: it is a map. The `no-tests` finding of `devai analyze` stays the CI check.

#### Writing tests with AI (`--file ... --ai`)

```bash
devai test --file src/stats.py --ai            # propose a new test file
devai test --file src/stats.py --ai --apply    # create it, after your "y"
devai test --file src/stats.py --ai --dry-run  # see what would be sent
```

- **What is sent:** the source file and up to 2 test files that already cover it (so the AI copies their style and imports), whole and with secrets redacted, plus the detected test framework and the names no test mentions yet.
- **Only new files.** To extend an existing test file, use `devai fix --file tests/test_stats.py --ask "add tests for percent"`.
- **The proposal is rejected whole** if the new path is outside the project, already exists, or is ignored by `.gitignore`; if its **name** wouldn't be found by a test runner (`test_*.py`, `*_test.py`, `*.test.js`, `*.spec.ts`, or a `__tests__` folder) or doesn't contain the source file's name; if it's in another language; or if the content is empty, over 300 lines, holds a secret or a redacted line, or isn't valid Python.
- **`--apply` creates the file after you type `y`, and never overwrites.** The file is created exclusively, so even one that appears at the last moment is kept. Missing folders (like `tests/`) are created and included in the undo command, e.g. `Undo with: rm tests/test_stats.py && rmdir tests`.
- **DevAI never runs the generated tests.** It prints a run command it builds itself from your test framework (`pytest …`, `npx jest …`, `npx vitest run …`), never one copied from the AI. Tests are code: review them before you run them.

### Finding missing documentation

`devai docs` shows where documentation seems to be missing, locally and for free. Nothing is sent anywhere and nothing is executed.

```bash
devai docs                 # text report
devai docs --format json   # for scripts
```

- **Python names without a docstring** (parsed with `ast`): the module itself, shown as `(module)`, public top-level functions and classes, and the public methods of public classes. Names starting with `_` are skipped, and so are private modules like `_internal.py`.
- **JavaScript and TypeScript exports without JSDoc:** `export function`, `export default function`, `export class`, `export const f = () =>`, `module.exports = function`, `exports.f = ...`. Only a `/** ... */` block right above counts, because that's what editors show; a `//` comment doesn't. Exports are found by pattern, not parsed, so `export { a, b }` and `export const Button = memo(...)` are not seen.
- **The README:** whether it has sections for installation, usage, tests and license, found by heading words in English or Portuguese (`Getting started`, `Instalação`, `Como usar`...). A `LICENSE` file counts as the license section.
- **npm scripts the README runs that don't exist:** commands like `npm run <script>` or `pnpm run <script>`, and npm's `test` and `start` shortcuts, written in a code block or in inline code, whose script is in no `package.json` of the project. This one is a fact, not an estimate: that command fails. Prose isn't read, and Yarn and Bun are left out, because `yarn run` and `bun run` also run binaries and files.
- **Test files are left out:** tests explain themselves through their names.
- Always exits `0`: like `devai test`, it is a map. Not every name needs a docstring; use it to choose where to look.

#### Writing docs with AI (`--file ... --ai`)

```bash
devai docs --file src/stats.py --ai            # propose docstrings, shown as a diff
devai docs --file src/stats.py --ai --apply    # write them, after your "y"
devai docs --file src/stats.py --ai --dry-run  # see what would be sent
```

- **What is sent:** the file, whole and with secrets redacted, the names in it without docs (the ones `devai docs` lists) and the project summary. If nothing is missing, nothing is sent.
- **The AI writes only the text; DevAI places it.** A Python docstring goes right after the definition's header, with the body's indentation (the module's goes at the top, after any leading comments); a JSDoc block goes right above the export. Lines are wrapped at 79 columns. The docs follow the language of the file's own comments.
- **Proof that only documentation changed.** In Python, the code with its docstrings removed must parse to exactly the same syntax tree as before. In JavaScript and TypeScript, every addition must be a single `/** */` comment right above an export, with no code in it.
- **The proposal is rejected whole** if any text contains `"""` or `*/` (which would end the docstring or the comment, and could slip code in), a redacted line or a possible secret, or if the proof fails. Docs for a name DevAI didn't ask about are dropped and listed.
- **`--apply` works like `devai fix --apply`:** the file must be committed and unchanged, you type `y`, the write is atomic, and `git restore <file>` undoes it.
- **Docs can still be wrong.** DevAI proves the code is untouched, not that the text is true. In a real test, a free model described a `filter` backwards, calling the entries it keeps the ones it removes. Read the diff before you apply it.
- Only missing docs are written. To correct an existing docstring, use `devai fix --file X --ask "..."`.

#### Writing README sections with AI (`--readme --ai`)

```bash
devai docs --readme --ai            # propose the missing sections, shown as a diff
devai docs --readme --ai --apply    # add them (or create README.md), after your "y"
devai docs --readme --ai --dry-run  # see what would be sent
```

- **Which sections:** the ones `devai docs` finds missing, but only when the project backs them: installation and usage always, tests only if the project has tests, and the license never. Choosing a license is your decision, not the AI's.
- **What is sent:** the README (secrets redacted), the project summary and the scripts the project defines (`package.json` scripts, `[project.scripts]` in `pyproject.toml`), each with how it runs. No source code.
- **The AI writes each section's title and text; DevAI adds them** before the license section, or at the end, at the level of your README's own sections. Nothing already in the README changes: DevAI checks that every original line is still there, in order.
- **Commands are checked against the project.** A section is dropped, with the reason, if it runs an npm script that no `package.json` has, uses npm, pnpm or yarn in a project without a `package.json` (global installs aside), or pip, pytest, poetry or pipenv in a project without Python. Then `devai docs` runs on the new README: it must find each new section, with no new command that fails.
- **Rejected whole** for a redacted line, a possible secret, or HTML that runs code (a script tag, a `javascript:` link). Links the AI wrote are listed for you to check.
- **Without a README**, DevAI proposes a new `README.md` (title, a short description, the sections) and creates it after your `y`, exclusively, like test files; `rm README.md` undoes it.
- Only Markdown READMEs are extended.

### Proposing fixes

`devai fix` asks a free AI for a fix and shows it as a diff. It writes to your project only with `--apply`, after you type `y`, and only when every safety check passes.

```bash
devai fix --file src/stats.py --ask "percent() breaks when whole is 0"
devai fix --file src/stats.py --ask "..." --dry-run    # see what would be sent
devai fix --file src/stats.py --ask "..." --apply      # write it, after your "y"
```

- **You choose which files may change** (`--file`, 1 to 3, with the same checks as in `chat`). They are sent **whole**, so the AI can copy the exact text it replaces. Lines that may hold a secret are still redacted, and the request too.
- **Edits are "find and replace"**: each one names a file, the exact current text and its replacement. DevAI rejects the **whole** proposal, with the reason, if any edit:
  - changes a file you didn't name;
  - uses text that isn't found exactly once (zero or several matches);
  - touches a redacted line or would write the redaction marker;
  - would add a secret;
  - would leave a `.py` file with invalid syntax or a `.json` file with invalid JSON;
  - or adds up to too much (over 10 edits or 200 changed lines).
- A valid proposal is applied **in memory only**, to build the diff. The output also lists risks and how to verify the fix. A rejected proposal exits with code `3`.
- Consent, providers and options work as in `chat` (`--yes`, `--provider`, `--format json`).

#### Applying a fix (`--apply`)

DevAI shows the diff, then asks *"Apply this fix to 1 file (src/stats.py)? [y/N]"*. Only `y` writes. Layers of safety, each one able to stop the write:

1. **You approve in a terminal, every time.** `--apply` refuses to run without one, and `--yes` only skips the *send* question, never this one.
2. **You can always undo.** Each named file must be tracked by git with no pending changes (staged or not), checked *before* the AI is asked. DevAI then prints `Undo with: git restore <file>`.
3. **No corruption.** Files must be valid UTF-8. Line endings and permissions are kept.
4. **No overwriting your edits.** Right before writing, each file must still hold exactly the content the fix was proposed for, and still be clean in git.
5. **All or nothing.** Each file is written to a temporary file and swapped in atomically. If a later file fails, the earlier ones are restored.

DevAI only reads git: it never stages, commits or pushes. The tests the AI suggests are printed, never run. `--apply` can't be combined with `--dry-run` or `--format json`. Exit codes: `0` applied or declined, `2` a safety check stopped it (nothing written), `3` the AI failed, the proposal was rejected, or a write failed (and was rolled back).

### AI analysis

`devai analyze --ai` adds an AI analysis: a summary, risks, prioritized recommendations, and the limits of what it could judge. **It is always free.** There are two providers:

| Provider | How | Needs | Data |
|---|---|---|---|
| `opencode` (default) | Runs your own [OpenCode](https://opencode.ai) CLI with a free model (`opencode/space-bunny-free`) | `opencode` installed | The summary goes to OpenCode's free service |
| `ollama` | Calls a model on your computer through [Ollama](https://ollama.com) (`qwen3.5:9b`) | Ollama running, model pulled | Stays on your machine |

```bash
pip install -e ".[ai]"
devai analyze --ai --dry-run            # 1. see exactly what would be sent
devai analyze --ai                      # 2. OpenCode, after you confirm
devai analyze --ai --provider ollama    # or a local model, no question needed
```

How it works:

- **Free by construction.** With OpenCode, DevAI accepts only OpenCode's own free models (names ending in `-free`, or `big-pickle`). A paid model, or another provider configured in your OpenCode, is refused before anything runs. If OpenCode ever reports a non-zero cost for a run, DevAI treats it as an error. Ollama models are local, so they are always free.
- **No tools for the model.** OpenCode runs with an inline config that defines a `devai` agent with every permission denied, in an empty temporary directory. The model receives the summary and can't read files or run commands. Each run appears in your OpenCode history as "DevAI analysis".
- **Consent when data leaves the machine.** OpenCode (and an Ollama on another computer) sends the summary over the network, so DevAI prints the local report and asks `[y/N]` first. Outside a terminal it refuses unless you pass `--yes`. Local Ollama runs without asking.
- **Know the model's data policy.** Some free OpenCode models may use what you send to improve them. DevAI prints a note when the chosen model is one of them. The default, `space-bunny-free`, declares zero retention and no training.
- **Validated answer.** The model must answer in a fixed JSON structure (Pydantic schema), or the run reports an error instead of free text.
- **Never affects `--fail-on`.** Model answers vary between runs; exit codes stay deterministic. If the AI step fails, you still get the full local report, and the exit code is `3`.
- **Settings:** `DEVAI_AI_PROVIDER` (`opencode` or `ollama`, or `--provider`), `DEVAI_AI_MODEL`, and `OLLAMA_HOST` (same rules as Ollama, default `http://localhost:11434`). DevAI never reads or sends an API key.

#### What is sent

| Sent | Never sent |
|---|---|
| Project name (the directory name only) | File contents: source code, `.env`, configs |
| Languages, frameworks, file counts | Absolute paths (they reveal your username) |
| Dependency **names** per manifest | Dependency versions |
| Test summary, config file **names** | The full file list |
| Top-level directories and their file counts | Secrets (only the masked prefix, e.g. `AKIA…`) |
| Findings (rule, severity, message, file:line, masked evidence) and passed checks | Git history |

Rules behind this table:

- The package is built from an **allow-list**: each field is chosen explicitly, so new data never reaches the AI by accident. A test fails if the set of fields changes.
- Long lists are capped (50 findings, 20 manifests, 100 dependencies per manifest, 30 config files, 30 directories). Anything cut is listed under `truncated`.
- File and dependency names come from the analyzed project, so they are untrusted data. The model will receive them as data, with no tools to act on them.
- DevAI never loads a `.env` file. It runs inside the project it analyzes, so reading `./.env` would mean reading that project's secrets. The API key will come from an environment variable (Phase 3b).

`python -m devai` works the same as `devai`.

## Development

```bash
pytest               # tests
ruff check .         # lint
ruff format .        # format code
```

CI (GitHub Actions) runs lint, format check and tests on Python 3.11–3.14 for every push to `main` and every pull request.

Project layout:

```
src/devai/
├── cli.py            # arguments; runs analyzer → checks → report
├── report.py         # formats results as terminal text
├── json_report.py    # formats results as JSON
├── ai/
│   ├── context.py    # what an AI may receive: allow-list, size caps
│   ├── prompt.py     # fixed system prompt, delimited user message
│   ├── schema.py     # AIReport: the structure the model must answer with
│   ├── opencode_client.py   # free models via your `opencode run` (subprocess)
│   ├── ollama_client.py     # local models via Ollama's HTTP API (urllib)
│   ├── result.py     # AIRequest, AIResult, LLMClient interface (no dependencies)
│   ├── analysis.py   # the analysis task: prompt + context → AIRequest
│   └── settings.py   # provider, model, OLLAMA_HOST; rejects paid models
├── models.py         # data models (ProjectInfo, Finding, CheckReport...)
├── git.py            # small subprocess wrapper around the git CLI
└── analyzer/
    ├── project.py       # runs every step, builds ProjectInfo
    ├── files.py         # file listing (git or filesystem + .gitignore)
    ├── languages.py     # extension → language
    ├── dependencies.py  # manifest parsing
    ├── frameworks.py    # dependency → framework / test framework
    ├── testing.py       # test file conventions
    ├── config_files.py  # well-known configuration files
    └── structure.py     # files per top-level directory
└── checks/           # judges the analyzer's output (depends on analyzer, not vice versa)
    ├── runner.py          # runs every check, sorts findings
    ├── project_checks.py  # README, .gitignore, tests, exposed .env
    └── secrets.py         # secret patterns, file skipping, masking
├── chat/             # `devai chat`: file selection and the chat context
│   ├── retrieval.py       # local keyword search, --file checks
│   ├── context.py         # what a chat answer may receive: numbered lines, history
│   ├── ai.py              # the chat task: prompt, consent question, grounding
│   ├── schema.py          # ChatAnswer: answer, sources, suggested files
│   └── session.py         # the conversation: approval, /commands, history
├── fix/              # `devai fix`: proposals validated and shown as a diff
│   ├── context.py         # what a fix may receive: named files, whole, redacted
│   ├── ai.py              # the fix task: prompt, consent question
│   ├── schema.py          # FixProposal: find-and-replace edits, risks, tests
│   ├── edits.py           # validation and the in-memory diff
│   └── apply.py           # --apply: git and content checks, atomic all-or-nothing write
├── testmap/          # `devai test`: where tests seem to be missing
│   ├── pairing.py         # source ↔ test files by name words
│   └── symbols.py         # public Python names no test mentions
├── docmap/           # `devai docs`: where documentation seems to be missing
│   ├── python_docs.py     # public Python names without a docstring (ast)
│   ├── js_docs.py         # JS/TS exports without JSDoc (patterns)
│   └── readme.py          # README sections and npm scripts that don't exist
├── docgen/           # `devai docs --ai`: docs written by AI, placed by DevAI
│   ├── context.py         # what it may receive: one file, the names without docs
│   ├── ai.py              # the task: prompt, consent question
│   ├── schema.py          # DocsProposal: one text per name, notes
│   ├── lines.py           # cleaning, wrapping and inserting the text
│   ├── python_insert.py   # where docstrings go, and the syntax-tree proof
│   ├── js_insert.py       # where JSDoc goes: one comment per block
│   └── plan.py            # safety checks, placement and the diff (nothing written)
├── readmegen/        # `devai docs --readme --ai`: README sections written by AI
│   ├── context.py         # what it may receive (README, summary, scripts); which topics
│   ├── ai.py              # the task: prompt, consent question
│   ├── schema.py          # ReadmeProposal: sections (topic, heading, body), notes
│   └── plan.py            # checks, commands against the project, placement, the diff
├── testgen/          # `devai test --ai`: new test files proposed by AI
│   ├── context.py         # what it may receive: the source and its existing tests
│   ├── ai.py              # the task: prompt, consent question
│   ├── schema.py          # GeneratedTests: path, content, covers, notes
│   ├── validate.py        # path, name, language and content rules
│   └── create.py          # exclusive creation, undo and run commands
└── review/           # `devai review`: local checks on git changes
    ├── diff.py            # changed files and added lines, from git
    ├── checks.py          # secrets, .env, tests, debug statements, size
    ├── context.py         # what an AI review may receive: hunks, redaction, limits
    ├── ai.py              # the review task: prompt, consent question, grounding
    └── schema.py          # AIReviewReport: the structure the review must have
tests/
```

## Roadmap

| Phase | Name | Scope |
|---|---|---|
| 0 | Planning | Decisions, roadmap, minimal docs |
| 1 | Basic CLI | `devai --help`, `--version`, `analyze` (basic project info) |
| 1.5 | CI | GitHub Actions running the test suite |
| 2a | Project Scanner | Files, ignore rules, languages, structure |
| 2b | Stack Detection | Dependencies, frameworks, tests, configuration files |
| 2c | Findings | `Finding` model, first checks (missing tests, exposed `.env`, secrets), `--format json`, exit codes |
| 3a | AI Context Builder | Allow-listed, size-capped context; `--ai --dry-run` preview, no network |
| 3b | AI Analysis | `--ai`: consent, validated structured report, LLM client interface (first provider: Anthropic, removed in 3.6) |
| 3.5 | Local AI | `--provider ollama`: same context and report, local model, consent only when data leaves the machine |
| 3.6 | Free AI only | OpenCode free models via the `opencode` CLI (default); Anthropic removed; paid models refused |
| 4a | Local Review | `devai review`: secrets, `.env`, tests, debug leftovers and size in the current git changes; no AI |
| 4b | AI Review Context | Allow-listed hunks with secrets redacted and size limits; `review --ai --dry-run`, no network |
| 4c | AI Review | Free AI review of the changed code (OpenCode free models or Ollama), consent listing the files |
| 5a | Chat Context | Local file selection with reasons, `--file`, numbered and redacted lines; `chat --ask ... --dry-run`, no network |
| 5b | Contextual Chat | Interactive `devai chat`: approve files per question, AI can suggest files, history kept locally |
| 6a | Fix Proposals | `devai fix`: find-and-replace edits, strict validation, diff; nothing is written |
| 6b | Applying Fixes | `devai fix --apply`: diff first, explicit approval, clean-git and unchanged-file checks, atomic write; never commits |
| 7a | Missing Tests | `devai test`: source files without a matching test, Python names no test mentions; an estimate, nothing executed |
| 7b | Test Generation | `devai test --file X --ai`: a new test file, validated, created only after your "y", never overwriting, never run by DevAI |
| 8a | Documentation Gaps | `devai docs`: Python names without docstrings, JS/TS exports without JSDoc, README sections, npm scripts the README runs that don't exist; nothing sent |
| 8b | AI Docstrings | `devai docs --file X --ai`: docstrings and JSDoc proposed by a free AI, applied only if the code itself is unchanged, after your "y" |
| 8c | AI README | `devai docs --readme --ai`: missing README sections written by a free AI and added without editing a line, with every command checked against the project |
| 9 | Web Interface | FastAPI + React, Docker |
| 10 | GitHub Integration | Repositories, pull requests, issues |
| 11 | Agent System | Only if a real need appears |

The roadmap changes as the project teaches us things. Design decisions are recorded in [docs/decisions.md](docs/decisions.md).

## License

[MIT](LICENSE)
