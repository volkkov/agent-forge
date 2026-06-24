#!/usr/bin/env python3
"""
Agent Forge — evaluator

Reads data/candidates.json (produced by collect.py), fetches each
candidate's README, and asks the OpenAI API to judge whether it's
genuinely useful, hype, broken, or a duplicate — then categorizes it
and writes a bilingual one-line summary.

Merges results into data/repos.json, preserving first_seen for repos
that already exist there.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CANDIDATES_PATH = DATA_DIR / "candidates.json"
REPOS_PATH = DATA_DIR / "repos.json"
I18N_PATH = DATA_DIR / "i18n.json"

OPENROUTER_API_KEY = os.environ.get("OPENAI_API_KEY", "")  # secret name kept as OPENAI_API_KEY for continuity
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Tried in order. If the primary model errors out, is rate-limited, or times
# out, we fall through to the next one rather than skipping the repo entirely.
# All of these support OpenRouter's strict json_schema structured outputs.
MODEL_FALLBACK_CHAIN = [
    os.environ.get("OPENAI_MODEL", "openai/gpt-4.1"),
    "anthropic/claude-sonnet-4.5",
    "google/gemini-2.5-pro",
    "openai/gpt-4o-mini",
]

MAX_README_CHARS = 6000

EVAL_SYSTEM_PROMPT = """You are a skeptical technical reviewer for "Agent Forge", a directory \
of AI-agent repositories. Your job is to separate genuinely useful, working tools from hype, \
abandoned projects, and marketing fluff. You are not trying to be encouraging — you are trying \
to be accurate and save the reader time.

You will be given a repo's name, description, README excerpt, and basic metadata (stars, forks, \
last commit date, archived status). Judge it on:

1. Does the README describe a concrete, reproducible mechanism, or mostly buzzwords \
   ("revolutionary", "10x", "world's most powerful", unverifiable performance numbers)?
2. Is it actually maintained — recent commits, no sign of being abandoned mid-hype-cycle?
3. Are there any real risk signals: paid/closed backend behind an "open source" label, \
   misleading "free" claims, license terms that restrict the use the README implies, \
   crypto/wallet requirements not mentioned in the headline description, safety concerns?
4. Is this a near-duplicate of a well-known tool with no meaningful differentiation?

Fill in: category, verdict, a bilingual one-or-two-sentence summary of what it concretely does \
(no marketing language), bilingual reasoning for the verdict citing specific evidence from the \
README/metadata, any risk flags, and short kebab-case tags.

Keep summaries and reasons factual and specific. Never invent claims not supported by the \
provided text. If the README is mostly marketing copy with no concrete mechanism, that itself \
is evidence for a "hype" verdict — say so plainly."""

RESPONSE_SCHEMA = {
    "name": "agent_forge_verdict",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "trading", "marketing", "browser-automation", "content-video",
                    "agent-infra", "dev-tools", "data-research", "productivity",
                    "finance-ops", "other",
                ],
            },
            "verdict": {
                "type": "string",
                "enum": ["useful", "hype", "broken", "duplicate"],
            },
            "summary_en": {"type": "string"},
            "summary_ru": {"type": "string"},
            "verdict_reason_en": {"type": "string"},
            "verdict_reason_ru": {"type": "string"},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "category", "verdict", "summary_en", "summary_ru",
            "verdict_reason_en", "verdict_reason_ru", "risk_flags", "tags",
        ],
        "additionalProperties": False,
    },
}


def fetch_readme(owner, repo, default_branch="main"):
    for branch in (default_branch, "main", "master"):
        for filename in ("README.md", "readme.md", "Readme.md"):
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
            try:
                req = Request(url, headers={"User-Agent": "agent-forge-evaluator"})
                with urlopen(req, timeout=20) as resp:
                    return resp.read().decode("utf-8", errors="ignore")[:MAX_README_CHARS]
            except Exception:
                continue
    return ""


def call_openrouter(model, user_content):
    """Single attempt against one model. Returns parsed JSON dict, or raises
    on any failure (HTTP error, bad shape, bad JSON) so the caller can decide
    whether to fall through to the next model in the chain."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": EVAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
    }).encode("utf-8")

    req = Request(
        OPENROUTER_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/agent-forge",
            "X-Title": "Agent Forge",
        },
        method="POST",
    )

    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    raw_text = data["choices"][0]["message"]["content"]
    return json.loads(raw_text)


def call_evaluator(candidate, readme_text):
    user_content = f"""Repo: {candidate['id']}
Description: {candidate.get('description_raw', '')}
Stars: {candidate.get('stars', 0)}
Forks: {candidate.get('forks', 0)}
Last pushed: {candidate.get('last_commit_at', 'unknown')}
Created: {candidate.get('created_at', 'unknown')}
Archived: {candidate.get('archived', False)}

README excerpt:
{readme_text if readme_text else '(no README found)'}
"""

    for model in MODEL_FALLBACK_CHAIN:
        try:
            return call_openrouter(model, user_content)
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            print(f"  ! {model} failed (HTTP {e.code}): {body[:200]} — trying next model", file=sys.stderr)
        except (KeyError, IndexError) as e:
            print(f"  ! {model} returned an unexpected response shape: {e} — trying next model", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"  ! {model} returned unparseable JSON: {e} — trying next model", file=sys.stderr)
        except Exception as e:
            print(f"  ! {model} failed ({type(e).__name__}: {e}) — trying next model", file=sys.stderr)

    print(f"  ! All models in the fallback chain failed for {candidate['id']}", file=sys.stderr)
    return None


def derive_health(candidate):
    last = candidate.get("last_commit_at")
    if not last:
        return "dead"
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return "stale"
    age_days = (datetime.now(timezone.utc) - last_dt).days
    if candidate.get("archived"):
        return "dead"
    if age_days <= 60:
        return "active"
    if age_days <= 270:
        return "stale"
    return "dead"


def load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def main():
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    candidates = load_json(CANDIDATES_PATH, [])
    existing_repos = {r["id"]: r for r in load_json(REPOS_PATH, [])}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    updated = []

    for cand in candidates:
        repo_id = cand["id"]
        owner, repo = cand["owner"], cand["name"]
        print(f"Evaluating {repo_id}...")

        readme = fetch_readme(owner, repo, cand.get("default_branch", "main"))
        verdict_data = call_evaluator(cand, readme)
        time.sleep(1)  # be polite to the API

        if not verdict_data:
            print(f"  skipped (no evaluator output)")
            continue

        health = derive_health(cand)
        first_seen = existing_repos.get(repo_id, {}).get("first_seen", today)

        record = {
            "id": repo_id,
            "name": cand["name"],
            "url": cand["url"],
            "owner": cand["owner"],
            "description_raw": cand.get("description_raw", ""),
            "summary_en": verdict_data.get("summary_en", ""),
            "summary_ru": verdict_data.get("summary_ru", ""),
            "category": verdict_data.get("category", "other"),
            "tags": verdict_data.get("tags", []),
            "stars": cand.get("stars", 0),
            "forks": cand.get("forks", 0),
            "last_commit_at": cand.get("last_commit_at"),
            "created_at": cand.get("created_at"),
            "ci_status": "unknown",
            "health": health,
            "verdict": verdict_data.get("verdict", "hype"),
            "verdict_reason_en": verdict_data.get("verdict_reason_en", ""),
            "verdict_reason_ru": verdict_data.get("verdict_reason_ru", ""),
            "risk_flags": verdict_data.get("risk_flags", []),
            "source": cand.get("source", "github-search"),
            "first_seen": first_seen,
            "last_checked": today,
        }
        updated.append(record)

    # merge: keep manual-seed entries untouched unless re-evaluated, append/replace the rest
    merged = {r["id"]: r for r in existing_repos.values() if r.get("source") == "manual-seed"}
    for r in updated:
        merged[r["id"]] = r
    # carry over any previously-seen non-manual entries that weren't re-checked this run
    for repo_id, r in existing_repos.items():
        if repo_id not in merged:
            merged[repo_id] = r

    final_list = list(merged.values())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPOS_PATH, "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(final_list)} total repos to {REPOS_PATH} ({len(updated)} evaluated this run)")


if __name__ == "__main__":
    main()
