#!/usr/bin/env python3
"""
Daily dashboard builder.

Pipeline:
  1. Read profile + RSS feeds from /config.
  2. Pull recent headlines from each feed.
  3. Ask Grok (xAI) for a short "what's hot today" briefing — Grok has live web/X access.
  4. Ask Claude to write the final dashboard markdown using profile + RSS + Grok briefing.
  5. Save to dashboards/YYYY-MM-DD.md  (overwrites if same day).
  6. Delete any dashboard file older than 5 days (rolling window).
  7. Rebuild index.md with today's content inline + small links to the previous 4 days.
"""

from __future__ import annotations

import os
import sys
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import List

import feedparser
import requests
from anthropic import Anthropic

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DASH_DIR = ROOT / "dashboards"
DASH_DIR.mkdir(exist_ok=True)

PROFILE_PATH = CONFIG_DIR / "profile.md"
FEEDS_PATH = CONFIG_DIR / "feeds.txt"
INDEX_PATH = ROOT / "index.md"
README_PATH = ROOT / "README.md"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROLLING_WINDOW_DAYS = 5            # keep last 5 daily files; older ones deleted
HEADLINES_PER_FEED = 6              # how many recent items to pull from each feed
CLAUDE_MODEL = "claude-opus-4-5"    # final-writer model
GROK_MODEL = "grok-4"               # live-news briefer

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
XAI_API_KEY = os.environ.get("XAI_API_KEY")

if not ANTHROPIC_API_KEY:
    sys.exit("ERROR: ANTHROPIC_API_KEY not set (add it as a repo secret).")

# ---------------------------------------------------------------------------
# Step 1 — read config
# ---------------------------------------------------------------------------
def read_profile() -> str:
    return PROFILE_PATH.read_text(encoding="utf-8")

def read_feeds() -> List[str]:
    urls = []
    for line in FEEDS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls

# ---------------------------------------------------------------------------
# Step 2 — pull RSS headlines
# ---------------------------------------------------------------------------
def fetch_headlines(urls: List[str]) -> str:
    """Return a markdown-formatted block of recent headlines grouped by source."""
    blocks = []
    for url in urls:
        try:
            parsed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
            source = parsed.feed.get("title", url)
            items = []
            for entry in parsed.entries[:HEADLINES_PER_FEED]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:240].strip()
                if title:
                    items.append(f"- {title} ({link})\n  {summary}")
            if items:
                blocks.append(f"### {source}\n" + "\n".join(items))
        except Exception as e:
            print(f"  ! feed failed: {url} — {e}", file=sys.stderr)
    return "\n\n".join(blocks) if blocks else "(no RSS items fetched)"

# ---------------------------------------------------------------------------
# Step 3 — Grok briefing (optional; skipped if no key)
# ---------------------------------------------------------------------------
def grok_briefing(profile: str) -> str:
    """Ask Grok for a short freshness pass — live web + X signal."""
    if not XAI_API_KEY:
        return "(Grok skipped — no XAI_API_KEY set)"

    system = (
        "You are a research assistant providing a short, factual freshness briefing. "
        "Use live web and X data. Output 8-12 concise bullets max. No fluff, no preamble."
    )
    user = (
        f"Owner profile (for relevance filtering only — do NOT address them):\n\n"
        f"{profile}\n\n"
        f"Today is {datetime.now(timezone.utc).strftime('%A %d %B %Y')}.\n\n"
        f"Give me today's most relevant fresh items across: UK banking, AI in banking, "
        f"agentic AI production stories, FCA/regulatory news, Kerry/Ireland items, "
        f"luxury travel deals (safari/cruise), and Tralee greyhound racing fixtures. "
        f"Bullet format. Include source name in parentheses."
    )

    try:
        r = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
            },
            timeout=90,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ! Grok call failed: {e}", file=sys.stderr)
        return f"(Grok briefing unavailable: {e})"

# ---------------------------------------------------------------------------
# Step 4 — Claude writes the final dashboard
# ---------------------------------------------------------------------------


def claude_write_dashboard(profile: str, rss_block: str, grok_block: str) -> str:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    london_now = datetime.now(ZoneInfo("Europe/London"))
    today_str = london_now.strftime("%A %d %B %Y")
    refresh_label = london_now.strftime("%H:%M %Z")
    system = (
        "You are writing a personal daily dashboard in markdown. "
        "Follow the section order in the owner's profile exactly. "
        "Be specific, concrete, and grounded in the source material provided — "
        "do NOT invent stories. If a section has no fresh material, say so briefly "
        "and offer one evergreen suggestion. Use the tone described in the profile. "
        "Output ONLY the markdown body — no preamble, no code fences."
    )

    user = f"""# Owner Profile
{profile}

---

# Source material — RSS headlines (recent)
{rss_block}

---

# Source material — Grok live briefing
{grok_block}

---

# Your task
Write today's dashboard. Date: {today_str}. Refresh time: {refresh_label}.

Start with an H1 of:
# Personal Dashboard — {today_str}

Then a one-line italic note:
*Last refreshed: {today_str}, {refresh_label}*

Then the sections in the exact order specified in the owner profile.
End with a horizontal rule and one short closing line.
"""

    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()

# ---------------------------------------------------------------------------
# Step 5/6 — save dated file + prune rolling window
# ---------------------------------------------------------------------------
def save_today(dashboard_md: str) -> Path:
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = DASH_DIR / f"{today_iso}.md"
    path.write_text(dashboard_md + "\n", encoding="utf-8")
    print(f"  ✓ wrote {path.relative_to(ROOT)}")
    return path

def prune_old() -> List[Path]:
    """Delete dashboards older than ROLLING_WINDOW_DAYS. Return remaining sorted newest-first."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=ROLLING_WINDOW_DAYS - 1)
    kept = []
    for p in sorted(DASH_DIR.glob("*.md")):
        try:
            file_date = datetime.strptime(p.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            p.unlink()
            print(f"  ✗ pruned {p.relative_to(ROOT)} (older than {ROLLING_WINDOW_DAYS} days)")
        else:
            kept.append(p)
    kept.sort(key=lambda p: p.stem, reverse=True)
    return kept

# ---------------------------------------------------------------------------
# Step 7 — rebuild index.md (and README.md mirrors it)
# ---------------------------------------------------------------------------
def rebuild_index(dashboards_newest_first: List[Path]) -> None:
    if not dashboards_newest_first:
        INDEX_PATH.write_text("# Personal Dashboard\n\n_No dashboards yet._\n", encoding="utf-8")
        return

    today_path = dashboards_newest_first[0]
    today_content = today_path.read_text(encoding="utf-8")

    # Build the small "previous days" link bar
    prev_links = []
    for p in dashboards_newest_first[1:]:
        d = datetime.strptime(p.stem, "%Y-%m-%d")
        label = d.strftime("%a %d %b")
        prev_links.append(f"[{label}](dashboards/{p.name})")

    if prev_links:
        nav = "**Previous days:** " + " · ".join(prev_links) + "\n\n---\n\n"
    else:
        nav = ""

    INDEX_PATH.write_text(nav + today_content, encoding="utf-8")
    README_PATH.write_text(nav + today_content, encoding="utf-8")
    print(f"  ✓ rebuilt index.md (today + {len(prev_links)} prior link(s))")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("→ reading config")
    profile = read_profile()
    feeds = read_feeds()
    print(f"  {len(feeds)} feed(s) configured")

    print("→ fetching RSS headlines")
    rss_block = fetch_headlines(feeds)

    print("→ asking Grok for live briefing")
    grok_block = grok_briefing(profile)

    print("→ asking Claude to write dashboard")
    dashboard_md = claude_write_dashboard(profile, rss_block, grok_block)

    print("→ saving today's dashboard")
    save_today(dashboard_md)

    print("→ pruning old dashboards")
    remaining = prune_old()

    print("→ rebuilding index")
    rebuild_index(remaining)

    print("✓ done")

if __name__ == "__main__":
    main()
