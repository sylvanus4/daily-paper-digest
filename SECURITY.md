# Security Policy

## Data flow and egress

`daily-paper-digest` is local-first and makes the fewest network calls possible.
It talks to exactly these hosts, and only when reachable:

| Host | Purpose | Required? |
|------|---------|-----------|
| `huggingface.co` | Fetch the trending daily-papers list | No — falls back to arXiv, then to the bundled sample |
| `export.arxiv.org` | Fallback source for recent papers | No — falls back to the bundled sample |
| `api.anthropic.com` | Optional AI-assisted summaries | No — only called if you set `ANTHROPIC_API_KEY` |

There is **no telemetry, no analytics, and no other outbound traffic**. If you run
with `--offline`, the tool makes zero network calls and uses the bundled
`sample/daily_papers_fixture.json`.

## API keys and secrets

- The Anthropic API key is read **only** from the `ANTHROPIC_API_KEY` environment
  variable (locally) or from a GitHub Actions secret of the same name (CI).
- The key is never written to disk, never committed, and never printed. It is
  sent only to `api.anthropic.com` over HTTPS.
- No key is required to use the tool. Without one, summaries degrade to each
  paper's own abstract plus metadata.
- `.env` is git-ignored. Do not commit real keys.

## What the tool does NOT do

- Does not execute code from fetched papers or API responses.
- Does not read files outside its own repository directory.
- Does not require elevated permissions.

## Reporting a vulnerability

Open a GitHub issue describing the problem, or contact the repository maintainer
privately if the issue is sensitive. There is no bug-bounty program; this is a
community tool.
