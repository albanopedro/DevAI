# Security

DevAI reads your code, can send parts of it to an AI model, can write files and can post on GitHub. This page says what it protects, how, and where its limits are. Every point links to the decision that explains it in [docs/decisions.md](docs/decisions.md).

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's private reporting instead: the repository's **Security** tab → **Report a vulnerability**. Include what you ran, what happened and what you expected. Only the latest release (1.x) gets fixes.

## What DevAI protects, and how

| Risk | How DevAI handles it | Decisions |
|---|---|---|
| A secret reaches an AI model or a report | `.env` files are never read; lock, minified, binary and large files are skipped; every line that may hold a secret is replaced before any AI context is built; findings show only a masked prefix | D010, D021, D025 |
| Code leaves the machine without consent | AI contexts are allow-listed and size-capped; `--dry-run` shows them exactly; DevAI asks before sending to anything that isn't on this computer | D025, D031 |
| Paying for AI by accident | Only OpenCode's free models (or a local Ollama) are accepted; a model that reports a cost is an error | D032, D033 |
| The AI changes code it shouldn't | Answers are validated before any diff: text that must exist, files that were named, syntax that still parses; docs are proven docs-only (Python syntax tree unchanged; JSDoc as single comments) | D043, D049 |
| A write destroys work | Writes need a human `y` (or a confirmation in the page), only touch committed files with no pending changes, re-check the content right before writing, are atomic, and are undone with `git restore`; new files are created exclusively and never overwrite | D044, D047 |
| Instructions hidden in code, issues or pull requests (prompt injection) | Everything a model receives is data inside delimited tags; answers are grounded in what was actually sent, and anything else is dropped | D029, D040, D054 |
| Generated tests or code run on your machine | DevAI never runs project code or generated tests; it prints the command for you | D045, D047 |
| The local web server is used by another site | It listens on 127.0.0.1 only; every API call needs a token that is new at every start; the Host and Origin headers must be local; no CORS; a strict Content-Security-Policy; a page can name a proposal but never send the content to write | D051 |
| DevAI acts on GitHub | It runs only an allow-list of `gh` commands (never merge, create, close or approve), never holds a token, and posts one comment only after you read its exact text; mentions are neutralized | D052, D053 |

## Known limits

- **Secret detection is pattern-based.** Known token formats and generic `key = "value"` assignments are caught; an unusual secret can still slip through. Keep secrets out of tracked files.
- **AI text can be wrong.** DevAI proves *where* text goes and that code didn't change, not that the text is true: a real run documented a `filter` backwards. Read every diff before you approve it.
- **JavaScript is read by patterns, not parsed.** An `export function` line inside a template string would be taken for a real export.
- **The local server trusts this computer.** Anyone who can read your terminal (and so the token), or run programs as you, can use it.
- **Data sent to OpenCode follows the chosen free model's policy.** DevAI shows the model's data note before sending; Ollama keeps everything local.
