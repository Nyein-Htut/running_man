import re
import time
import threading
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

HEADERS = {"User-Agent": "RunningManIndex/6.0 (+https://render.com)"}

# Episode-number -> year boundaries (mirrors the original desktop tool)
YEAR_BOUNDARIES = [
    (23, "2010"), (74, "2011"), (126, "2012"), (178, "2013"),
    (227, "2014"), (279, "2015"), (331, "2016"), (383, "2017"),
    (432, "2018"), (483, "2019"), (535, "2020"), (585, "2021"),
    (634, "2022"), (686, "2023"), (734, "2024"), (783, "2025"),
]
DEFAULT_LATEST_YEAR = "2026"

ALL_YEARS = [y for _, y in YEAR_BOUNDARIES] + [DEFAULT_LATEST_YEAR]

# ---------------------------------------------------------------------------
# In-memory cache: { year: {"data": [...], "fetched_at": timestamp} }
# ---------------------------------------------------------------------------
_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 60 * 60 * 12  # 12 hours


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\[.*?\]", "", text).strip()


def get_year_for_episode(ep_num):
    for boundary, year in YEAR_BOUNDARIES:
        if ep_num <= boundary:
            return year
    return DEFAULT_LATEST_YEAR


def scrape_year(year, force=False):
    """Scrape (and cache) every episode row for a given year page."""
    with _CACHE_LOCK:
        cached = _CACHE.get(year)
        if not force and cached and (time.time() - cached["fetched_at"] < CACHE_TTL_SECONDS):
            return cached["data"]

    url = f"https://en.wikipedia.org/wiki/List_of_Running_Man_episodes_({year})"
    episodes = []

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for table in soup.find_all("table", class_="wikitable"):
                for row in table.find_all("tr"):
                    th_cells = row.find_all("th")
                    td_cells = row.find_all("td")

                    if th_cells and len(td_cells) >= 4:
                        ep_text = clean_text(th_cells[0].text)
                        if not ep_text.isdigit():
                            continue
                        episodes.append({
                            "Episode": ep_text,
                            "Year": year,
                            "Air Date": clean_text(td_cells[0].text),
                            "Title": clean_text(td_cells[1].text),
                            "Guest(s)": clean_text(td_cells[2].text) or "N/A",
                            "Teams": clean_text(td_cells[3].text) or "N/A",
                            "Mission": clean_text(td_cells[4].text) if len(td_cells) > 4 else "N/A",
                            "Results": clean_text(td_cells[5].text) if len(td_cells) > 5 else "N/A",
                        })
    except requests.RequestException:
        pass

    with _CACHE_LOCK:
        # Don't overwrite good cached data with an empty result from a transient failure
        if episodes or year not in _CACHE:
            _CACHE[year] = {"data": episodes, "fetched_at": time.time()}
        return _CACHE[year]["data"]


def get_all_episodes():
    all_eps = []
    for year in ALL_YEARS:
        all_eps.extend(scrape_year(year))
    return all_eps


def warm_cache_async():
    def _run():
        for year in ALL_YEARS:
            scrape_year(year)
    threading.Thread(target=_run, daemon=True).start()


# Kick off a background warm-up as soon as the process starts so the first
# real user search doesn't have to wait on 17 sequential requests.
warm_cache_async()

# ---------------------------------------------------------------------------
# FAQ / "popular missions" presets — canned keyword searches
# ---------------------------------------------------------------------------
FAQ_PRESETS = [
    {
        "slug": "spy",
        "label": "Spy Missions",
        "emoji": "🕵️",
        "keywords": ["spy", "secret agent", "double agent", "undercover", "agent"],
    },
    {
        "slug": "horror",
        "label": "Horror & Halloween",
        "emoji": "👻",
        "keywords": ["horror", "halloween", "ghost", "zombie", "haunted"],
    },
    {
        "slug": "wedding",
        "label": "Weddings & Romance",
        "emoji": "💍",
        "keywords": ["wedding", "blind date", "couple", "marriage", "love"],
    },
    {
        "slug": "newyear",
        "label": "New Year Specials",
        "emoji": "🎆",
        "keywords": ["new year"],
    },
    {
        "slug": "mystery",
        "label": "Mystery & Traitor",
        "emoji": "🔎",
        "keywords": ["mystery", "detective", "criminal", "traitor", "backstabber", "death note"],
    },
    {
        "slug": "school",
        "label": "School Episodes",
        "emoji": "🏫",
        "keywords": ["school", "classroom", "student"],
    },
    {
        "slug": "racestart",
        "label": "Race Start / Relay",
        "emoji": "🏁",
        "keywords": ["race start", "relay"],
    },
    {
        "slug": "sports",
        "label": "Sports Day",
        "emoji": "🏆",
        "keywords": ["sports day", "athletics", "olympic"],
    },
]


def matches_keywords(ep, keywords):
    haystack = " ".join([
        ep.get("Title", ""), ep.get("Mission", ""), ep.get("Guest(s)", "")
    ]).lower()
    return any(k in haystack for k in keywords)


# ---------------------------------------------------------------------------
# Guest headshot lookup — Wikipedia's public REST API (no scraping of Google
# Images / arbitrary sites: that would violate ToS, get IP-blocked quickly,
# and return photos with unclear licensing). Wikipedia's summary endpoint is
# free to call, stable, and its images carry known licenses.
# ---------------------------------------------------------------------------
GUEST_IMAGE_CACHE = {}
GUEST_IMAGE_LOCK = threading.Lock()
GUEST_IMAGE_TTL_SECONDS = 60 * 60 * 24 * 7  # 1 week — headshots rarely change

WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"


def split_guest_names(raw):
    """'Guest(s)' cell is a free-text, comma/'and'-separated list of names."""
    if not raw or raw == "N/A":
        return []
    raw = re.sub(r"\(.*?\)", "", raw)  # drop parenthetical roles/notes
    parts = re.split(r",| and |&", raw)
    names = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]
    seen = set()
    out = []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


def fetch_guest_image(name):
    """Look up a guest's Wikipedia thumbnail + page link. Cached per name."""
    key = name.lower()
    with GUEST_IMAGE_LOCK:
        cached = GUEST_IMAGE_CACHE.get(key)
        if cached and (time.time() - cached["fetched_at"] < GUEST_IMAGE_TTL_SECONDS):
            return cached["data"]

    result = {"name": name, "image": None, "wiki_url": None, "extract": None}

    try:
        # Step 1: resolve to the best-matching Wikipedia page title.
        search_res = requests.get(
            WIKI_SEARCH_URL,
            params={
                "action": "query", "list": "search", "srsearch": name,
                "format": "json", "srlimit": 1,
            },
            headers=HEADERS, timeout=8,
        )
        search_hits = search_res.json().get("query", {}).get("search", [])
        page_title = search_hits[0]["title"] if search_hits else name

        # Step 2: fetch the summary (thumbnail image lives here).
        summary_res = requests.get(
            WIKI_SUMMARY_URL.format(requests.utils.quote(page_title)),
            headers=HEADERS, timeout=8,
        )
        if summary_res.status_code == 200:
            summary = summary_res.json()
            thumbnail = summary.get("thumbnail", {}).get("source")
            result["image"] = thumbnail
            result["wiki_url"] = summary.get("content_urls", {}).get("desktop", {}).get("page")
            result["extract"] = clean_text(summary.get("extract", ""))[:160] or None
    except (requests.RequestException, ValueError, KeyError, IndexError):
        pass

    with GUEST_IMAGE_LOCK:
        GUEST_IMAGE_CACHE[key] = {"data": result, "fetched_at": time.time()}
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", faq_presets=FAQ_PRESETS)


@app.route("/api/episode/<int:ep_num>")
def api_episode(ep_num):
    if ep_num <= 0:
        return jsonify({"error": "Episode number must be positive."}), 400

    year = get_year_for_episode(ep_num)
    episodes = scrape_year(year)
    match = next((e for e in episodes if e["Episode"] == str(ep_num)), None)

    if not match:
        # retry once with a forced refresh in case the show page changed recently
        episodes = scrape_year(year, force=True)
        match = next((e for e in episodes if e["Episode"] == str(ep_num)), None)

    if not match:
        return jsonify({"error": f"No record found for Episode {ep_num}."}), 404

    return jsonify(match)


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"error": "Query cannot be empty."}), 400
    if len(query) < 2:
        return jsonify({"error": "Type at least 2 characters."}), 400

    all_eps = get_all_episodes()
    results = [
        e for e in all_eps
        if query in e["Title"].lower()
        or query in e["Guest(s)"].lower()
        or query in e["Mission"].lower()
    ]
    results.sort(key=lambda e: int(e["Episode"]))
    return jsonify({"query": query, "count": len(results), "results": results[:60]})


@app.route("/api/faq")
def api_faq_list():
    return jsonify([{k: v for k, v in p.items() if k != "keywords"} for p in FAQ_PRESETS])


@app.route("/api/faq/<slug>")
def api_faq_results(slug):
    preset = next((p for p in FAQ_PRESETS if p["slug"] == slug), None)
    if not preset:
        return jsonify({"error": "Unknown FAQ category."}), 404

    all_eps = get_all_episodes()
    results = [e for e in all_eps if matches_keywords(e, preset["keywords"])]
    results.sort(key=lambda e: int(e["Episode"]))
    return jsonify({
        "label": preset["label"],
        "emoji": preset["emoji"],
        "count": len(results),
        "results": results[:60],
    })


@app.route("/api/guest-images")
def api_guest_images():
    """Batch cast-photo lookup, e.g. /api/guest-images?names=Kim Jong-kook,Song Ji-hyo"""
    raw = request.args.get("names", "").strip()
    if not raw:
        return jsonify({"error": "Provide a comma-separated 'names' param."}), 400

    names = split_guest_names(raw)[:12]  # keep batches sane
    guests = [fetch_guest_image(n) for n in names]
    return jsonify({"guests": guests})


@app.route("/api/status")
def api_status():
    with _CACHE_LOCK:
        cached_years = sorted(_CACHE.keys())
        total = sum(len(v["data"]) for v in _CACHE.values())
    return jsonify({
        "cached_years": cached_years,
        "total_episodes_cached": total,
        "server_time": datetime.utcnow().isoformat() + "Z",
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
