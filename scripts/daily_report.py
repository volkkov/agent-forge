#!/usr/bin/env python3
"""
Agent Forge — daily report

Reads data/repos.json and writes a short Markdown report of what
changed today: newly added useful repos, anything that flipped to
hype/broken, and a one-line summary. Appended to reports/YYYY-MM-DD.md
and used as the GitHub Action job summary.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPOS_PATH = DATA_DIR / "repos.json"
REPORTS_DIR = ROOT / "reports"


def load_repos():
    with open(REPOS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    repos = load_repos()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    new_today = [r for r in repos if r.get("first_seen") == today]
    checked_today = [r for r in repos if r.get("last_checked") == today]
    useful = [r for r in checked_today if r["verdict"] == "useful"]
    hype = [r for r in checked_today if r["verdict"] == "hype"]
    broken = [r for r in checked_today if r["verdict"] == "broken"]
    duplicate = [r for r in checked_today if r["verdict"] == "duplicate"]

    lines = []
    lines.append(f"# Agent Forge — daily report ({today})")
    lines.append("")
    lines.append(f"- Repos checked today: **{len(checked_today)}**")
    lines.append(f"- New repos discovered today: **{len(new_today)}**")
    lines.append(f"- Useful: **{len(useful)}** · Hype watch: **{len(hype)}** · Broken: **{len(broken)}** · Duplicate: **{len(duplicate)}**")
    lines.append("")

    if new_today:
        lines.append("## New today")
        lines.append("")
        for r in sorted(new_today, key=lambda x: -x.get("stars", 0)):
            badge = {"useful": "✅", "hype": "⚠️", "broken": "❌", "duplicate": "♻️"}.get(r["verdict"], "•")
            lines.append(f"- {badge} **[{r['name']}]({r['url']})** ({r['category']}) — {r['summary_en']}")
        lines.append("")

    if hype:
        lines.append("## Flagged as hype")
        lines.append("")
        for r in hype:
            lines.append(f"- **{r['name']}** — {r['verdict_reason_en']}")
        lines.append("")

    if broken:
        lines.append("## Flagged as broken")
        lines.append("")
        for r in broken:
            lines.append(f"- **{r['name']}** — {r['verdict_reason_en']}")
        lines.append("")

    report = "\n".join(lines)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{today}.md"
    report_path.write_text(report, encoding="utf-8")

    # Also write to GITHUB_STEP_SUMMARY if running in a GitHub Action
    import os
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(report + "\n")

    print(report)


if __name__ == "__main__":
    main()
