#!/usr/bin/env python3
"""
Standalone, one-off scraper: builds data/episode_titles.json by pulling real
episode titles from MyDramaList (https://mydramalist.com/25565-running-man).

WHY THIS IS A SEPARATE SCRIPT, NOT PART OF THE LIVE APP
---------------------------------------------------------
MyDramaList sits behind bot protection that appears to block plain
server-side requests from datacenter IPs (like Render's) — the live app's
attempts to fetch episode titles were silently failing 100% of the time.
Running this script from your own machine/home network avoids that, so you
get a real, reliable dataset once, commit it, and the live app just reads
from the committed JSON instead of hitting MyDramaList on every request.

USAGE
-----
    cd runningman
    python3 scripts/scrape_mdl_titles.py

Re-run it occasionally (e.g. monthly) to pick up newly aired episodes — it's
resumable and only fetches episodes missing from data/episode_titles.json,
so a re-run is fast and won't hammer MyDramaList.

Options:
    --start N       First episode number to try (default: 1)
    --end N         Last episode number to try (default: auto-detect by
                     probing forward until a real 404, so you don't need to
                     know the current max episode number)
    --delay SECONDS Delay between requests (default: 1.5) — please don't set
                     this too low, MyDramaList is a small community site and
                     hammering it is a good way to get blocked outright.
    --output PATH   Where to write the JSON (default: data/episode_titles.json)
    --force         Re-fetch episodes even if already present in the output file

If you start seeing lots of "BLOCKED" messages, stop the script, wait a
while, and try again later — that means MyDramaList's bot protection has
kicked in for your IP too, and continuing will only make it worse.
"""
import argparse
import json
import os
import re
import sys
import time

import requests

MDL_SHOW_SLUG = "25565-running-man"
MDL_EPISODE_URL = f"https://mydramalist.com/{MDL_SHOW_SLUG}/episode/{{}}"

# A realistic browser header set. MyDramaList's protection is largely aimed
# at obvious bots (missing/blank UA, datacenter-only headers), so requesting
# from a normal residential/home connection with these headers tends to work
# even though the exact same request from a server often gets blocked.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_OGTITLE_RE = re.compile(r'property="og:title"\s+content="([^"]+)"')
_PREFIX_RE = re.compile(r"^Running Man Episode\s+\d+\s*[:\-]\s*(.+)$", re.IGNORECASE)


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\[.*?\]", "", text).strip()


def fetch_one(session, ep_num):
    """Returns (status, title_or_none).
    status is one of: "ok", "no_title", "not_found", "blocked", "error".
    """
    try:
        res = session.get(MDL_EPISODE_URL.format(ep_num), headers=HEADERS, timeout=10)
    except requests.RequestException as exc:
        return "error", None

    if res.status_code == 404:
        return "not_found", None
    if res.status_code in (403, 429) or res.status_code >= 500:
        return "blocked", None
    if res.status_code != 200:
        return "error", None

    match = _OGTITLE_RE.search(res.text)
    if not match:
        return "no_title", None

    og_title = clean_text(match.group(1))
    prefix_match = _PREFIX_RE.match(og_title)
    if not prefix_match:
        return "no_title", None

    candidate = prefix_match.group(1).strip()
    if not candidate or re.match(r"^Episode\s+\d+$", candidate, re.IGNORECASE):
        return "no_title", None  # MDL just echoed "Episode N" back — no real title set

    return "ok", candidate


def load_existing(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=None, help="omit to auto-detect the current last episode")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "..", "data", "episode_titles.json"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output_path = os.path.abspath(args.output)
    titles = load_existing(output_path)
    print(f"Loaded {len(titles)} existing entries from {output_path}")

    session = requests.Session()

    ep_num = args.start
    consecutive_not_found = 0
    consecutive_blocked = 0
    fetched_count = 0
    AUTO_DETECT_STOP_AFTER = 5  # stop probing once this many consecutive 404s are hit

    while True:
        if args.end is not None and ep_num > args.end:
            break

        key = str(ep_num)
        if key in titles and not args.force:
            ep_num += 1
            continue

        status, title = fetch_one(session, ep_num)

        if status == "ok":
            titles[key] = title
            print(f"  #{ep_num}: {title}")
            consecutive_not_found = 0
            consecutive_blocked = 0
            fetched_count += 1
        elif status == "no_title":
            titles[key] = None
            print(f"  #{ep_num}: (no distinct title on MDL)")
            consecutive_not_found = 0
            consecutive_blocked = 0
            fetched_count += 1
        elif status == "not_found":
            consecutive_not_found += 1
            print(f"  #{ep_num}: 404 not found ({consecutive_not_found} in a row)")
            if args.end is None and consecutive_not_found >= AUTO_DETECT_STOP_AFTER:
                print(f"Hit {AUTO_DETECT_STOP_AFTER} consecutive 404s — assuming episode "
                      f"list ends around #{ep_num - AUTO_DETECT_STOP_AFTER}. Stopping.")
                break
        elif status == "blocked":
            consecutive_blocked += 1
            print(f"  #{ep_num}: BLOCKED (HTTP status suggests rate limiting/bot protection)")
            if consecutive_blocked >= 3:
                print("Getting blocked repeatedly — stopping early to avoid making it worse.")
                print(f"Progress saved. Re-run this script later to pick up where it left off "
                      f"(next unscraped episode is #{ep_num}).")
                break
            time.sleep(args.delay * 5)  # back off harder before retrying
            continue
        else:
            print(f"  #{ep_num}: request error, skipping for now")

        save(output_path, titles)  # save after every fetch so interruptions never lose progress
        ep_num += 1
        time.sleep(args.delay)

    print(f"\nDone. Fetched {fetched_count} new entries this run. "
          f"Total in {output_path}: {len(titles)}")


if __name__ == "__main__":
    main()
