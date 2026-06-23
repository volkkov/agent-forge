# Agent Forge

A daily-curated directory of AI-agent repositories — trading bots, marketing
agents, browser automation, video generation, agent infrastructure, and more —
filtered for what's actually maintained and useful, not hype.

**Live site:** _add your GitHub Pages URL here once deployed_

## Why this exists

Lists like "10 GitHub repos that print money while you sleep" circulate
constantly on social media. The repos they link to are often real, but the
framing rarely is — README marketing language, unverified performance
claims, and abandoned projects get the same spotlight as genuinely solid
tools. Agent Forge runs every candidate repo through an AI evaluator that
checks for concrete mechanisms, real maintenance activity, and risk
signals (closed backends behind an "open source" label, misleading "free"
claims, restrictive licenses, abandoned CI), then sorts the result into
categories you can actually browse.

Repos that don't hold up are not deleted — they're shown in a separate
"hype & broken" section with the specific reason, so the filtering process
itself stays auditable.

## How it works
scripts/collect.py    → searches GitHub (topics + keywords) and known

awesome-lists for candidate repos

scripts/evaluate.py   → fetches each README, asks an LLM (OpenAI) to judge

verdict / category / risk flags / bilingual summary

scripts/daily_report.py → writes reports/YYYY-MM-DD.md with what changed

.github/workflows/daily.yml → runs the above on a daily cron, commits

data/repos.json, and deploys site/ to GitHub Pages

All evaluated data lives in [`data/repos.json`](data/repos.json) — see
[`docs/SCHEMA.md`](docs/SCHEMA.md) for the full record shape and the
verdict definitions (`useful` / `hype` / `broken` / `duplicate`).

## Local development

```bash
# regenerate site data manually (requires GITHUB_TOKEN + OPENAI_API_KEY)
export GITHUB_TOKEN=...
export OPENAI_API_KEY=...
python scripts/collect.py
python scripts/evaluate.py
python scripts/daily_report.py

# serve the site locally
python -m http.server 8080
# open http://localhost:8080/site/index.html
```

The site (`site/`) is plain HTML/CSS/JS with no build step — it fetches
`data/repos.json` and `data/i18n.json` directly at runtime.

## Contributing

Found a repo that should be in here, or one that's flagged wrong? Open an
issue with the repo link and why — the evaluator re-checks flagged entries
on the next daily run.

## License

MIT — see [LICENSE](LICENSE).
