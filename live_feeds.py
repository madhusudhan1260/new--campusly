"""Live hackathon and internship listings pulled from public third-party feeds.

Both sources are fetched over plain HTTP and cached in memory for a while --
these are real external services, not something this app controls, so a
failure (timeout, format change, source down) must never break the
Hackathons/Internships pages. Every fetch function returns [] on failure
instead of raising, and serves the last good result while it's still
reasonably fresh if the source is temporarily unreachable.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

import requests

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SECONDS = 30 * 60
_HTML_TAG_RE = re.compile(r"<[^>]+>")

DEVPOST_URL = "https://devpost.com/api/hackathons"
SIMPLIFY_INTERNSHIPS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json"
)


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
    return _HTML_TAG_RE.sub("", text or "").strip()


def fetch_live_hackathons(limit: int = 6) -> list[dict]:
    """Currently-open hackathons from Devpost's public listings API."""

    def _fetch() -> list[dict]:
        response = requests.get(
            DEVPOST_URL,
            params={"status[]": "open", "order_by": "recently-added", "per_page": limit},
            headers={
                "Accept": "application/json",
                "Referer": "https://devpost.com/hackathons",
                "User-Agent": "Mozilla/5.0 (compatible; CampuslyBot/1.0; +https://github.com/madhusudhan1260)",
            },
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
                    "title": h.get("title"),
                    "url": h.get("url"),
                    "location": (h.get("displayed_location") or {}).get("location") or "Online",
                    "thumbnail": thumb,
                    "time_left": h.get("time_left_to_submission"),
                    "dates": h.get("submission_period_dates"),
                    "prize": _strip_html(h.get("prize_amount") or ""),
                    "themes": [t.get("name") for t in (h.get("themes") or [])][:3],
                    "registrations": h.get("registrations_count") or 0,
                }
            )
        return results

    return _cached(f"hackathons:{limit}", _fetch)


def fetch_live_internships(limit: int = 8) -> list[dict]:
    """Active internship postings from the community-maintained SimplifyJobs feed.

    That repo's bots continuously check real company career pages and mark a
    listing inactive once it's gone -- this is the same JSON their own site
    and several other internship trackers are built on.
    """

    def _fetch() -> list[dict]:
        response = requests.get(SIMPLIFY_INTERNSHIPS_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
        active = [d for d in data if d.get("active") and d.get("is_visible", True)]
        active.sort(key=lambda d: d.get("date_posted", 0), reverse=True)

        results = []
        for d in active[:limit]:
            posted_ts = d.get("date_posted")
            posted = (
                datetime.fromtimestamp(posted_ts, tz=timezone.utc).strftime("%d %b %Y") if posted_ts else None
            )
            results.append(
                {
                    "title": d.get("title"),
                    "company": d.get("company_name"),
                    "url": d.get("url"),
                    "locations": ", ".join((d.get("locations") or [])[:2]) or "Location not listed",
                    "terms": ", ".join(d.get("terms") or []),
                    "sponsorship": d.get("sponsorship"),
                    "posted": posted,
                }
            )
        return results

    return _cached(f"internships:{limit}", _fetch)
