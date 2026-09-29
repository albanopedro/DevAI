# DevAI

[![CI](https://github.com/albanopedro/DevAI/actions/workflows/ci.yml/badge.svg)](https://github.com/albanopedro/DevAI/actions/workflows/ci.yml)

AI-powered developer assistant for code analysis, review, testing and software engineering automation.

> **Status:** early development (Phase 2a: project scanner).

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
pip install -e ".[dev]"
```

## Usage

```bash
devai --help
devai --version
devai analyze            # current directory
devai analyze path/to/project
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

Structure:
  public/   3 files
  src/     47 files
  (root)    9 files
```

### How files are found

DevAI only reads file **names** at this stage, never file contents (the one exception is `.gitignore`).

- **Inside a git repository** (or any subdirectory of one), git lists the files: tracked files plus untracked files that aren't ignored. Every ignore rule applies, including nested `.gitignore` files, `.git/info/exclude` and your global excludes file. Shown as `(git)`.
- **Otherwise**, DevAI walks the directory, skips common generated folders (`node_modules`, `.venv`, `__pycache__`, `dist`, `build`...) and applies the **root** `.gitignore` if there is one. Shown as `(filesystem)` or `(filesystem + .gitignore)`. Limitation: `.gitignore` files in subdirectories are not read in this mode.

Languages are detected by file extension. Data and docs formats (JSON, YAML, Markdown) are not counted as languages.

`python -m devai` works the same as `devai`.

Exit codes: `0` success, `1` no command given, `2` path is not a directory.

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
├── cli.py            # argument parsing, calls the analyzer, prints the report
├── report.py         # formats results as terminal text
├── models.py         # data models (ProjectInfo, LanguageStat, ...)
├── git.py            # small subprocess wrapper around the git CLI
└── analyzer/
    ├── project.py    # runs every step, builds ProjectInfo
    ├── files.py      # file listing (git or filesystem + .gitignore)
    ├── languages.py  # extension → language
    └── structure.py  # files per top-level directory
tests/
```

## Roadmap

| Phase | Name | Scope |
|---|---|---|
| 0 | Planning | Decisions, roadmap, minimal docs |
| 1 | Basic CLI | `devai --help`, `--version`, `analyze` (basic project info) |
| 1.5 | CI | GitHub Actions running the test suite |
| 2a | Project Scanner | Files, ignore rules, languages, structure |
| 2b | Project Checks | Dependencies, frameworks, config, tests, first security checks, `--format json`, exit codes |
| 3 | AI Analysis | Opt-in (`--ai`): context builder, LLM client interface, structured report |
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
