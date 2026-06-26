# Agent Forge

**A daily-curated directory of AI-agent repositories** — trading bots, design
agents, browser automation, video generation, agent infrastructure, and
more — filtered for what's actually maintained and useful, not hype.

🌐 **Live site:** [agent-forge-nine-iota.vercel.app](https://agent-forge-nine-iota.vercel.app)
📡 **Daily finds on Telegram:** [@AgentForgeSignal](https://t.me/AgentForgeSignal)

![status](https://img.shields.io/badge/status-live-5EEAD4)
![updates](https://img.shields.io/badge/updates-daily-2DA89A)
![license](https://img.shields.io/badge/license-MIT-blue)

## Why this exists

Lists like "10 GitHub repos that print money while you sleep" circulate
constantly on social media. The repos they link to are often real, but the
framing rarely is — README marketing language, unverified performance
claims, and abandoned projects get the same spotlight as genuinely solid
tools.

Agent Forge runs every candidate repo through an AI evaluator that checks
for a concrete mechanism, real maintenance activity, and risk signals
(closed backends behind an "open source" label, misleading "free" claims,
restrictive licenses, abandoned CI, implausible timelines), then sorts the
result into categories you can actually browse:

- 💰 Trading & DeFi
- 📣 Marketing & Ads
- 🌐 Browser Automation
- 🎬 Content & Video Gen
- 🎨 Design & UI/UX
- 🧠 Agent Infrastructure
- 🛠️ Dev Tools
- 📊 Data & Research
- ✅ Productivity
- 💼 Finance & Ops

Repos that don't hold up are not deleted — they're shown in a separate
"hype & broken" section on the site with the specific reason, so the
filtering process itself stays auditable. Nothing gets buried; you can see
exactly why something didn't make the cut.

## How it works
scripts/collect.py      → searches GitHub (topics + keywords) and known

awesome-lists for candidate repos

scripts/evaluate.py     → fetches each README, asks an LLM (via OpenRouter,

free tier with a fallback chain) to judge

verdict / category / risk flags / bilingual summary

scripts/daily_report.py → writes reports/YYYY-MM-DD.md, posts new "useful"

finds to the Telegram channel

.github/workflows/daily.yml → runs the above on a daily cron, commits

data/repos.json, and syncs it into site/data/

for the live Vercel deployment

All evaluated data lives in [`data/repos.json`](data/repos.json) — see
[`docs/SCHEMA.md`](docs/SCHEMA.md) for the full record shape and the
verdict definitions (`useful` / `hype` / `broken` / `duplicate`).

The site itself (`site/`) is plain HTML/CSS/JS with no build step and a
small Three.js ambient background — it fetches `site/data/repos.json` and
`site/data/i18n.json` directly at runtime, in English and Russian.

## Local development

```bash
# regenerate site data manually (requires GITHUB_TOKEN + OPENAI_API_KEY,
# where OPENAI_API_KEY is actually an OpenRouter key — see scripts/evaluate.py)
export GITHUB_TOKEN=...
export OPENAI_API_KEY=...
python scripts/collect.py
python scripts/evaluate.py
python scripts/daily_report.py

# serve the site locally
python -m http.server 8080
# open http://localhost:8080/site/index.html
```

## Contributing

Found a repo that should be in here, or one that's flagged wrong? Open an
issue with the repo link and why — the evaluator re-checks flagged entries
on a future run. Pull requests for the site, the evaluator prompt, or new
discovery sources (more awesome-lists, more search topics) are welcome.

## License

MIT — see [LICENSE](LICENSE).
