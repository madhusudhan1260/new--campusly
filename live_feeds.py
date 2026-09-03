"""Live hackathon and internship listings pulled from public third-party feeds.

Mirrors the source list used by the author's other project, hackathon-hub
(github: madhusudhan1260) -- Devpost + MLH for hackathons, Remotive + a
merged GitHub-hosted internship tracker for internships. Internshala and
Unstop are deliberately left out: that project's own collector code notes
neither has a public API and scraping them would violate their ToS.

Every source is fetched over plain HTTP and cached in memory for a while --
these are real external services this app doesn't control, so a failure
(timeout, format change, source down) must never break the Hackathons/
Internships pages. Each fetch function returns [] on failure instead of
raising, and _cached() serves the last good result while a source is
temporarily unreachable rather than blanking the section.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from itertools import zip_longest

import requests
from bs4 import BeautifulSoup

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SECONDS = 30 * 60
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_UA = "Mozilla/5.0 (compatible; CampuslyBot/1.0; +https://github.com/madhusudhan1260) hackathon/internship aggregator"

DEVPOST_URL = "https://devpost.com/api/hackathons"
MLH_SEASON_URL = "https://www.mlh.com/seasons/{year}/events"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
GITHUB_TRACKER_URL = "https://raw.githubusercontent.com/SuryaHarikrishnan/2027-internship-tracker/master/data/listings.json"


def _cached(key: str, fetch_fn, ttl: int = _CACHE_TTL_SECONDS) -> list[dict]:
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < ttl:
        return cached[1]
    try:
        data = fetch_fn()
    except Exception:
        return cached[1] if cached else []
    _CACHE[key] = (now, data)
    return data


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text or "").replace("&nbsp;", " ").strip()


def _dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = (item.get("url") or item.get("title") or "").lower().rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _interleave(lists: list[list[dict]]) -> list[dict]:
    """Round-robin merge so one prolific source can't crowd out the rest."""
    out = []
    for row in zip_longest(*lists):
        for item in row:
            if item is not None:
                out.append(item)
    return out


# --------------------------------------------------------------- Hackathons


def _fetch_devpost(limit: int) -> list[dict]:
    response = requests.get(
        DEVPOST_URL,
        params={"status[]": "open", "order_by": "recently-added", "per_page": limit},
        headers={"Accept": "application/json", "Referer": "https://devpost.com/hackathons", "User-Agent": _UA},
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    results = []
    for h in payload.get("hackathons", [])[:limit]:
        thumb = h.get("thumbnail_url") or ""
        if thumb.startswith("//"):
            thumb = "https:" + thumb
        results.append(
            {
                "source": "Devpost",
                "title": h.get("title"),
                "url": h.get("url"),
                "location": (h.get("displayed_location") or {}).get("location") or "Online",
                "thumbnail": thumb,
                "time_left": h.get("time_left_to_submission"),
                "dates": h.get("submission_period_dates"),
                "prize": _strip_html(h.get("prize_amount") or ""),
                "themes": [t.get("name") for t in (h.get("themes") or []) if t.get("name")][:3],
                "registrations": h.get("registrations_count") or 0,
            }
        )
    return results


def _mlh_seasons() -> list[int]:
    today = date.today()
    return [today.year, today.year + 1] if today.month >= 6 else [today.year]


def _fetch_mlh(limit: int) -> list[dict]:
    results: list[dict] = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": _UA, "Accept": "text/html"})
        for year in _mlh_seasons():
            if len(results) >= limit:
                break
            try:
                response = session.get(MLH_SEASON_URL.format(year=year), timeout=10)
                response.raise_for_status()
            except requests.RequestException:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for card in soup.select('[itemtype*="schema.org/Event"]'):
                url = _mlh_prop(card, "url") or card.get("href", "")
                if not url:
                    continue
                title = _mlh_title(card)
                if not title:
                    continue

                mode = {
                    "OnlineEventAttendanceMode": "Online",
                    "OfflineEventAttendanceMode": "Offline",
                    "MixedEventAttendanceMode": "Hybrid",
                }.get((_mlh_prop(card, "eventAttendanceMode") or "").rsplit("/", 1)[-1], "")
                location = _mlh_location(card)
                free = (_mlh_prop(card, "isAccessibleForFree") or "").lower() == "true"
                start = _mlh_prop(card, "startDate")

                results.append(
                    {
                        "source": "MLH",
                        "title": title,
                        "url": url,
                        "location": location or (mode or "Online"),
                        "thumbnail": "",
                        "time_left": None,
                        "dates": start,
                        "prize": "Free entry" if free else "",
                        "themes": ["MLH", "Student"],
                        "registrations": 0,
                    }
                )
                if len(results) >= limit:
                    break
    return results


def _mlh_prop(card, name: str) -> str:
    el = card.select_one(f'[itemprop="{name}"]')
    if el is None:
        return ""
    return (el.get("content") or el.get_text(" ", strip=True) or "").strip()


def _mlh_title(card) -> str:
    heading = card.select_one("h1, h2, h3, h4, h5")
    if heading:
        text = heading.get_text(" ", strip=True)
        if text:
            return text
    img = card.select_one("img[alt]")
    if img:
        alt = (img.get("alt") or "").replace(" background", "").strip()
        if alt:
            return alt
    return ""


def _mlh_location(card) -> str:
    city = _mlh_prop(card, "addressLocality")
    region = _mlh_prop(card, "addressRegion")
    country = _mlh_prop(card, "addressCountry")
    parts = [p for p in (city, region, country) if p]
    return ", ".join(parts) if parts else _mlh_prop(card, "location")


def fetch_live_hackathons(limit: int = 8) -> list[dict]:
    """Currently-open hackathons merged from Devpost and MLH."""

    def _fetch() -> list[dict]:
        per_source = []
        for source_fetch in (_fetch_devpost, _fetch_mlh):
            try:
                per_source.append(source_fetch(limit))
            except Exception:
                per_source.append([])
        return _dedupe(_interleave(per_source))[:limit]

    return _cached(f"hackathons:{limit}", _fetch)


# -------------------------------------------------------------- Internships


def _fetch_remotive(limit: int) -> list[dict]:
    response = requests.get(REMOTIVE_URL, params={"search": "intern"}, headers={"User-Agent": _UA}, timeout=10)
    response.raise_for_status()
    items = response.json().get("jobs") or []

    results = []
    for item in items:
        job_type = (item.get("job_type") or "").lower()
        title = (item.get("title") or "").strip()
        url = item.get("url") or ""
        if not title or not url:
            continue
        if job_type != "internship" and "intern" not in title.lower():
            continue
        results.append(
            {
                "source": "Remotive",
                "title": title,
                "company": item.get("company_name") or "",
                "url": url,
                "locations": item.get("candidate_required_location") or "Remote",
                "terms": "",
                "sponsorship": "",
                "posted": (item.get("publication_date") or "")[:10] or None,
            }
        )
        if len(results) >= limit:
            break
    return results


def _fetch_github_tracker(limit: int) -> list[dict]:
    response = requests.get(GITHUB_TRACKER_URL, headers={"User-Agent": _UA}, timeout=15)
    response.raise_for_status()
    data = response.json()
    items = data if isinstance(data, list) else data.get("listings", [])

    active = [d for d in items if d.get("active", True) and d.get("is_visible", True) is not False]
    active.sort(key=lambda d: d.get("date_posted", 0), reverse=True)

    results = []
    for d in active[:limit]:
        title = (d.get("title") or "").strip()
        url = d.get("url") or ""
        if not title or not url:
            continue
        posted_ts = d.get("date_posted")
        posted = None
        if posted_ts:
            try:
                posted = datetime.fromtimestamp(int(posted_ts), tz=timezone.utc).strftime("%d %b %Y")
            except (TypeError, ValueError, OSError):
                posted = None
        results.append(
            {
                "source": d.get("source") or "GitHub Tracker",
                "title": title,
                "company": d.get("company_name") or "",
                "url": url,
                "locations": ", ".join((d.get("locations") or [])[:2]) or "Location not listed",
                "terms": ", ".join(d.get("terms") or []),
                "sponsorship": d.get("sponsorship") or "",
                "posted": posted,
            }
        )
    return results


def fetch_live_internships(limit: int = 10) -> list[dict]:
    """Active internships merged from Remotive and a community GitHub tracker."""

    def _fetch() -> list[dict]:
        per_source = []
        for source_fetch in (_fetch_github_tracker, _fetch_remotive):
            try:
                per_source.append(source_fetch(limit))
            except Exception:
                per_source.append([])
        return _dedupe(_interleave(per_source))[:limit]

    return _cached(f"internships:{limit}", _fetch)
