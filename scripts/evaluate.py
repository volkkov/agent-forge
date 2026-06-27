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

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Multiple OpenRouter keys (e.g. your own + friends' free-tier keys) let us
# spread evaluation load across several independent daily quotas instead of
# being capped at one account's ~50 req/day. Set OPENAI_API_KEY to your main
# key and, optionally, OPENAI_API_KEY_2 / OPENAI_API_KEY_3 / ... for backups.
# Each candidate tries keys in order and falls through on quota/auth errors,
# so a single exhausted key doesn't stop the run.
def _load_api_keys():
    keys = []
    primary = os.environ.get("OPENAI_API_KEY", "")
    if primary:
        keys.append(primary)
    i = 2
    while True:
        extra = os.environ.get(f"OPENAI_API_KEY_{i}", "")
        if not extra:
            break
        keys.append(extra)
        i += 1
    return keys


OPENROUTER_API_KEYS = _load_api_keys()

# Tried in order. If the primary model errors out, is rate-limited, or times
# out, we fall through to the next one rather than skipping the repo entirely.
# openrouter/free auto-picks among whatever free models currently support the
# request's needs (including structured outputs) — this is the most reliable
# choice since explicit :free model slugs rotate out of the free tier within
# weeks. The explicit :free models below are a backup only.
MODEL_FALLBACK_CHAIN = [
    os.environ.get("OPENAI_MODEL", "openrouter/free"),
    "deepseek/deepseek-r1:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-7b-instruct:free",
]

# Free-tier accounts get ~50 requests/day total (across all free models
# combined) until $10+ has ever been added to the account, after which the
# daily floor rises to 1000. Keep this comfortably under 50 so one run can't
# burn the whole day's quota by itself — remaining candidates get picked up
# automatically tomorrow (collect.py re-discovers them, already-evaluated
# ids are simply re-checked or skipped based on sort priority below).
MAX_EVALUATIONS_PER_RUN = int(os.environ.get("MAX_EVALUATIONS_PER_RUN", "20"))

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

Important: "broken" means the project is abandoned, archived, or its CI/build is failing —
not merely that the README lacks marketing polish or independent benchmarks. A repo with
high stars, a recent last-pushed date, and an active release history is evidence of a real,
maintained project even if its README is sparse or the excerpt you received got truncated.
In that case, prefer "useful" (or "hype" if the README itself is mostly unverifiable claims)
over "broken". Reserve "broken" for concrete evidence of abandonment: an explicit archival
notice, a redirect to a successor repo, failing CI badges, or a last-pushed date that is old
relative to today's date.

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
                    "design-ux", "memory-context", "agent-infra", "dev-tools",
                    "data-research", "productivity", "finance-ops", "other",
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


def validate_verdict_quality(data):
    """Catches the failure modes we saw from weak free-tier models: empty
    required text fields, or leaked reasoning/prompt artifacts spilling into
    a field instead of the actual content. Raises ValueError to trigger
    fallback to the next model if the response doesn't look usable."""
    text_fields = ["summary_en", "summary_ru", "verdict_reason_en", "verdict_reason_ru"]
    leak_markers = ["let's think", "[end eval]", "they expect:", "format:"]
    for field in text_fields:
        value = (data.get(field) or "").strip()
        if not value:
            raise ValueError(f"empty required field: {field}")
        if any(marker in value.lower() for marker in leak_markers):
            raise ValueError(f"field {field} looks like a leaked prompt/reasoning artifact: {value[:80]!r}")
    for tag in data.get("tags", []):
        if len(tag) > 60 or "]" in tag or "{" in tag:
            raise ValueError(f"malformed tag, likely leaked artifact: {tag[:80]!r}")


def call_openrouter(model, api_key, user_content):
    """Single attempt against one model+key pair. Returns parsed JSON dict,
    or raises on any failure (HTTP error, bad shape, bad JSON, low-quality
    output) so the caller can decide whether to fall through to the next
    model/key."""
    payload = json.dumps({
        "model": model,
        "max_tokens": 1200,
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
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/agent-forge",
            "X-Title": "Agent Forge",
        },
        method="POST",
    )

    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    raw_text = data["choices"][0]["message"]["content"]
    if not raw_text or not raw_text.strip():
        raise ValueError(f"empty response content (finish_reason={data['choices'][0].get('finish_reason')})")
    parsed = json.loads(raw_text)
    validate_verdict_quality(parsed)
    return parsed


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
        for key_index, api_key in enumerate(OPENROUTER_API_KEYS):
            try:
                return call_openrouter(model, api_key, user_content)
            except HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")
                print(f"  ! {model} (key #{key_index+1}) failed (HTTP {e.code}): {body[:200]} — trying next", file=sys.stderr)
            except (KeyError, IndexError) as e:
                print(f"  ! {model} (key #{key_index+1}) returned an unexpected response shape: {e} — trying next", file=sys.stderr)
            except json.JSONDecodeError as e:
                print(f"  ! {model} (key #{key_index+1}) returned unparseable JSON: {e} — trying next", file=sys.stderr)
            except Exception as e:
                print(f"  ! {model} (key #{key_index+1}) failed ({type(e).__name__}: {e}) — trying next", file=sys.stderr)
            time.sleep(2)  # give the next free-tier provider/key a clean slate

    print(f"  ! All model/key combinations failed for {candidate['id']}", file=sys.stderr)
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
    if not OPENROUTER_API_KEYS:
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    candidates = load_json(CANDIDATES_PATH, [])
    existing_repos = {r["id"]: r for r in load_json(REPOS_PATH, [])}

    # Prioritize candidates we haven't evaluated before, then by stars, so a
    # capped run still makes forward progress on new repos instead of
    # re-checking the same already-known ones every day.
    def sort_key(c):
        already_seen = c["id"] in existing_repos
        return (already_seen, -(c.get("stars") or 0))

    candidates = sorted(candidates, key=sort_key)[:MAX_EVALUATIONS_PER_RUN]

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
