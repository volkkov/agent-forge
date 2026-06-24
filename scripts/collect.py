#!/usr/bin/env python3
"""
Agent Forge — collector

Searches GitHub for candidate AI-agent repositories (via topics and
keyword search) and parses known "awesome-*" list repos for additional
links. Writes raw candidates to data/candidates.json for the evaluator
script to process.

Does NOT call the Anthropic API — this script is intentionally dumb
and cheap. All judgment calls happen in evaluate.py.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CANDIDATES_PATH = DATA_DIR / "candidates.json"
REPOS_PATH = DATA_DIR / "repos.json"

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Topics and keyword searches used to discover new candidate repos.
SEARCH_TOPICS = [
    "claude-skill",
    "claude-code-skill",
    "agent-skills",
    "ai-agent",
    "autonomous-agent",
    "llm-agent",
    "mcp-server",
    "design-system",
    "ui-generation",
    "llm-router",
    "ai-coding-agent",
    "prompt-engineering",
]

SEARCH_KEYWORDS = [
    "claude code skill",
    "autonomous trading agent",
    "ai agent browser automation",
    "llm router agent",
    "ai design system agent",
    "ux ui agent skill",
    "free llm api",
    "ai video generation agent",
    "claude code plugin",
]

# Known curated lists to mine for additional candidate links.
# Format: (owner/repo, path to raw markdown file on the default branch)
AWESOME_LISTS = [
    ("ComposioHQ/awesome-claude-skills", "README.md"),
    ("travisvn/awesome-claude-skills", "README.md"),
    ("The-Swarm-Corporation/Awesome-Swarms-List", "README.md"),
    ("VoltAgent/awesome-agent-skills", "README.md"),
    ("heilcheng/awesome-agent-skills", "README.md"),
    ("cheahjs/free-llm-api-resources", "README.md"),
    ("hesreallyhim/awesome-claude-code", "README.md"),
    ("Shubhamsaboo/awesome-llm-apps", "README.md"),
]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "agent-forge-collector",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def gh_get(url, params=None):
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"  ! HTTP {e.code} for {url}: {body[:200]}", file=sys.stderr)
        return None


def search_repos_by_topic(topic, per_page=20):
    print(f"Searching topic: {topic}")
    data = gh_get(
        f"{GITHUB_API}/search/repositories",
        params={"q": f"topic:{topic}", "sort": "updated", "order": "desc", "per_page": per_page},
    )
    if not data:
        return []
    return data.get("items", [])


def search_repos_by_keyword(keyword, per_page=15):
    print(f"Searching keyword: {keyword}")
    data = gh_get(
        f"{GITHUB_API}/search/repositories",
        params={"q": keyword, "sort": "updated", "order": "desc", "per_page": per_page},
    )
    if not data:
        return []
    return data.get("items", [])


def fetch_readme_links(owner_repo, path):
    url = f"https://raw.githubusercontent.com/{owner_repo}/HEAD/{path}"
    req = Request(url, headers={"User-Agent": "agent-forge-collector"})
    try:
        with urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ! could not fetch {url}: {e}", file=sys.stderr)
        return []
    # crude extraction of github.com/<owner>/<repo> links
    pattern = r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:[\)\]\s\"'>]|$)"
    found = set()
    for m in re.finditer(pattern, text):
        owner, repo = m.group(1), m.group(2).rstrip(".,")
        if owner.lower() in ("topics", "search", "sponsors", "marketplace", "orgs"):
            continue
        found.add(f"{owner}/{repo}")
    return sorted(found)


def repo_meta(full_name):
    data = gh_get(f"{GITHUB_API}/repos/{full_name}")
    return data


def to_candidate(repo_json):
    if not repo_json or repo_json.get("message"):
        return None
    return {
        "id": repo_json["full_name"].lower(),
        "name": repo_json["name"],
        "url": repo_json["html_url"],
        "owner": repo_json["owner"]["login"],
        "description_raw": repo_json.get("description") or "",
        "stars": repo_json.get("stargazers_count", 0),
        "forks": repo_json.get("forks_count", 0),
        "last_commit_at": repo_json.get("pushed_at"),
        "created_at": repo_json.get("created_at"),
        "default_branch": repo_json.get("default_branch", "main"),
        "archived": repo_json.get("archived", False),
        "source": "github-search",
    }


def main():
    candidates = {}

    if not GITHUB_TOKEN:
        print("WARNING: no GITHUB_TOKEN set, requests will be heavily rate-limited.", file=sys.stderr)

    for topic in SEARCH_TOPICS:
        for item in search_repos_by_topic(topic):
            cand = to_candidate(item)
            if cand:
                candidates[cand["id"]] = cand
        time.sleep(1)

    for kw in SEARCH_KEYWORDS:
        for item in search_repos_by_keyword(kw):
            cand = to_candidate(item)
            if cand:
                candidates[cand["id"]] = cand
        time.sleep(1)

    for list_repo, path in AWESOME_LISTS:
        links = fetch_readme_links(list_repo, path)
        print(f"  found {len(links)} links in {list_repo}")
        for full_name in links:
            key = full_name.lower()
            if key in candidates:
                continue
            meta = repo_meta(full_name)
            cand = to_candidate(meta)
            if cand:
                cand["source"] = "awesome-list"
                candidates[cand["id"]] = cand
            time.sleep(0.5)

    # Heuristic pre-filter: drop archived repos, drop near-empty descriptions,
    # drop long-abandoned + low-star noise. Final judgment is the evaluator's job.
    filtered = []
    for cand in candidates.values():
        if cand.get("archived"):
            continue
        if len(cand.get("description_raw", "")) < 10:
            continue
        filtered.append(cand)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(filtered)} candidates to {CANDIDATES_PATH}")


if __name__ == "__main__":
    main()
