# DevAI

[![CI](https://github.com/albanopedro/DevAI/actions/workflows/ci.yml/badge.svg)](https://github.com/albanopedro/DevAI/actions/workflows/ci.yml)

AI-powered developer assistant for code analysis, review, testing and software engineering automation.

> **Status:** early development (Phase 3b: AI analysis).

## Goal

DevAI analyzes a software project: it maps the structure, languages, frameworks, dependencies, tests and configuration, flags likely problems, and uses AI to interpret what it found.

It is a learning and portfolio project, and it grows in small, tested phases.

## Principles

- **Deterministic first, AI second.** `devai analyze` works offline with no API key. AI is opt-in and only receives a structured, reviewable context.
- **Privacy by default.** Honors `.gitignore`, never reads `.env` files, never prints secrets, and never sends code to an external API without explicit consent.
- **User in control.** DevAI never applies code changes without showing a diff and asking for approval, and never commits or pushes.

## Installation

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"        # DevAI + test tools (only dependency: pathspec)
pip install -e ".[dev,ai]"     # also the optional AI analysis (Anthropic SDK)
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
devai analyze --ai                # AI analysis by Claude, after asking for confirmation
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

### AI analysis

`devai analyze --ai` adds an analysis by Claude (Anthropic): a summary, risks, prioritized recommendations, and the limits of what it could judge. It needs the optional extra and an API key:

```bash
pip install -e ".[ai]"
export ANTHROPIC_API_KEY=...        # never put it in a file inside a project
devai analyze --ai --dry-run        # 1. see exactly what would be sent
devai analyze --ai                  # 2. send it, after confirming
```

How it works:

- **You confirm every time.** DevAI prints the local report, then asks before sending anything (`[y/N]`, "no" by default). Outside a terminal (CI, pipes) it refuses unless you pass `--yes`.
- **One request per run** to `claude-opus-5-5` with effort `medium`. Override with `DEVAI_AI_MODEL` and `DEVAI_AI_EFFORT` (`low`, `medium`, `high`, `xhigh`, `max`). If the model declines for policy reasons, the API retries on a fallback model, and the report shows which model answered.
- **Validated answer.** The model must answer in a fixed structure (Pydantic schema), or the run reports an error instead of free text.
- **Costs money.** Each run sends about 1–2 thousand tokens and receives a few thousand (including the model's reasoning). The report prints the real token counts.
- **Never affects `--fail-on`.** Model answers vary between runs; exit codes stay deterministic.
- **The deterministic report always comes first.** If the AI step fails, you still get it, and the exit code is `3`.
- Data sent to Anthropic is subject to Anthropic's data usage and retention policies.

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
│   ├── client.py     # the only code that calls an external service
│   ├── result.py     # AIResult, AIError, LLMClient interface (no dependencies)
│   └── settings.py   # DEVAI_AI_MODEL / DEVAI_AI_EFFORT
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
| 3b | AI Analysis | `--ai`: consent, Claude call, validated structured report, LLM client interface |
| 3.5 | Local AI | Ollama provider behind the same interface |
| 4 | Code Review | `devai review`: analyze `git diff` |
| 5 | Contextual Chat | `devai chat` |
| 6 | Fix Suggestions | `devai fix`: proposed diff, manual approval |
| 7 | Test Generation | `devai test` |
| 8 | Documentation | `devai docs` |
| 9 | Web Interface | FastAPI + React, Docker |
| 10 | GitHub Integration | Repositories, pull requests, issues |
| 11 | Agent System | Only if a real need appears |

The roadmap changes as the project teaches us things. Design decisions are recorded in [docs/decisions.md](docs/decisions.md).

## License

[MIT](LICENSE)
