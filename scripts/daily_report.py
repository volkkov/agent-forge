#!/usr/bin/env python3
"""
Agent Forge — daily report

Reads data/repos.json and writes a short Markdown report of what
changed today: newly added useful repos, anything that flipped to
hype/broken, and a one-line summary. Appended to reports/YYYY-MM-DD.md
and used as the GitHub Action job summary.

Also posts a short digest of today's new "useful" finds to a Telegram
channel, if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set. Hype/broken
finds stay on the site's transparency section only — the channel is a
signal feed, not a firehose.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPOS_PATH = DATA_DIR / "repos.json"
REPORTS_DIR = ROOT / "reports"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SITE_URL = os.environ.get("SITE_URL", "https://agent-forge-nine-iota.vercel.app")

CATEGORY_LABELS = {
    "trading": "Trading & DeFi",
    "marketing": "Marketing & Ads",
    "browser-automation": "Browser Automation",
    "content-video": "Content & Video Gen",
    "design-ux": "Design & UI/UX",
    "agent-infra": "Agent Infrastructure",
    "dev-tools": "Dev Tools",
    "data-research": "Data & Research",
    "productivity": "Productivity",
    "finance-ops": "Finance & Ops",
    "other": "Other",
}


def load_repos():
    with open(REPOS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID) — skipping post.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        print("Posted digest to Telegram.")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"  ! Telegram post failed (HTTP {e.code}): {body[:300]}")


def build_telegram_digest(new_useful, today):
    if not new_useful:
        return None
    lines = [f"<b>Agent Forge — {len(new_useful)} new find{'s' if len(new_useful) != 1 else ''} ({today})</b>", ""]
    for r in sorted(new_useful, key=lambda x: -x.get("stars", 0))[:10]:
        cat = CATEGORY_LABELS.get(r["category"], r["category"])
        stars = r.get("stars", 0)
        star_str = f"{stars/1000:.1f}k" if stars >= 1000 else str(stars)
        lines.append(f'⭐ {star_str} · <a href="{r["url"]}">{r["name"]}</a> ({cat})')
        lines.append(r.get("summary_en", ""))
        lines.append("")
    lines.append(f'<a href="{SITE_URL}">See the full board →</a>')
    return "\n".join(lines)


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

    new_useful_today = [r for r in new_today if r["verdict"] == "useful"]
    digest = build_telegram_digest(new_useful_today, today)
    if digest:
        send_telegram_message(digest)
    else:
        print("No new useful finds today — skipping Telegram post.")


if __name__ == "__main__":
    main()
