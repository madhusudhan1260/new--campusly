"""Campusly -- a small campus portal: Hackathons, Internships, Health and a
Lost & Found board, behind student / admin / super-admin login.

Single Flask app (not a package) on purpose -- this is a curated-board demo,
not a production system, and a handful of route files would be more
indirection than the app actually needs.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
import uuid
from datetime import date, datetime, timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_wtf import CSRFProtect

from auth import current_user, hash_password, login_required, role_required
from extensions import db
from live_feeds import fetch_live_hackathons, fetch_live_internships
from models import (
    APPLICATION_STATUSES,
    BLOOD_GROUPS,
    MOOD_EMOJI,
    MOODS,
    SOS_TYPES,
    Application,
    BloodDonor,
    BloodPing,
    BloodRequest,
    Bookmark,
    CATEGORIES,
    Claim,
    CounselorRequest,
    Doctor,
    HealthAppointment,
    Item,
    MedicineReminder,
    MoodEntry,
    Opportunity,
    Profile,
    SOSRequest,
    SupportMessage,
    Team,
    TeamMember,
    User,
)

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ITEM_CATEGORIES = ["Electronics", "Bags", "Books", "Clothing", "ID Cards", "Keys", "Bottles", "Other"]
LOST_FOUND_OFFICE = os.environ.get("LOST_FOUND_OFFICE", "the DOSS office").strip()

HACKATHON_MODES = ["Online", "Offline", "Hybrid"]
INTERNSHIP_MODES = ["Remote", "Onsite", "Hybrid"]

# Same buckets hackathon-hub filters prize/stipend by.
PRIZE_BUCKETS = {"0-10k": (0, 10_000), "10k-1l": (10_000, 100_000), "1l+": (100_000, None)}
SORT_OPTIONS = ("deadline", "reward", "recent", "title")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest").strip()
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Real institution facts -- placeholders on purpose. Set these in .env rather
# than trusting a made-up number for something students might call in a
# genuine emergency.
HEALTH_CENTER_NAME = os.environ.get("HEALTH_CENTER_NAME", "Campus Health Center")
HEALTH_CENTER_PHONE = os.environ.get("HEALTH_CENTER_PHONE", "Set HEALTH_CENTER_PHONE in .env")
HEALTH_CENTER_TIMINGS = os.environ.get("HEALTH_CENTER_TIMINGS", "Set HEALTH_CENTER_TIMINGS in .env")
HEALTH_CENTER_LOCATION = os.environ.get("HEALTH_CENTER_LOCATION", "Set HEALTH_CENTER_LOCATION in .env")

APPOINTMENT_SLOTS = [
    "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM",
    "02:00 PM", "02:30 PM", "03:00 PM", "03:30 PM", "04:00 PM", "04:30 PM",
]

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "mvv.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # 6 MB

db.init_app(app)
csrf = CSRFProtect(app)


@app.context_processor
def inject_user():
    return {
        "logged_in_user": current_user(),
        "today": date.today(),
        "notifications_count": len(_notification_items()),
    }


# ---------------------------------------------------------------------------
# Auth -- removed. Every visitor shares one account (see auth.py). These
# three redirects exist only so an old bookmark to /login, /signup or
# /logout lands somewhere sensible instead of 404ing.
# ---------------------------------------------------------------------------

@app.route("/signup", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
@app.post("/logout")
def _auth_redirect():
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Dashboard
#
# Every number here comes straight from the database -- open opportunity
# counts, doctors, lost items -- nothing is a placeholder. "Recommended for
# you" only shows a match percentage when it's a real one, computed from
# categories the student has actually bookmarked; with no bookmarks yet it
# falls back to "closing soon" / "recently posted" rather than inventing a
# number that would look personalized but isn't.
# ---------------------------------------------------------------------------

def _relative_time(dt: datetime) -> str:
    seconds = (datetime.utcnow() - dt).total_seconds()
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(seconds // 86400)
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return dt.strftime("%d %b")


def _dashboard_activity(limit: int = 6) -> list[dict]:
    events = []
    for op in Opportunity.query.order_by(Opportunity.created_at.desc()).limit(4).all():
        events.append(
            {
                "icon": "🚀" if op.kind == "hackathon" else "💼",
                "label": "New hackathon posted" if op.kind == "hackathon" else "New internship posted",
                "detail": op.title,
                "time": _relative_time(op.created_at),
                "ts": op.created_at,
            }
        )
    for item in Item.query.order_by(Item.created_at.desc()).limit(3).all():
        events.append(
            {
                "icon": "🔎",
                "label": "New Lost & Found report",
                "detail": item.name,
                "time": _relative_time(item.created_at),
                "ts": item.created_at,
            }
        )
    for doc in Doctor.query.filter_by(available=True).order_by(Doctor.created_at.desc()).limit(2).all():
        events.append(
            {
                "icon": "🏥",
                "label": "Doctor available",
                "detail": f"{doc.name} is available now.",
                "time": _relative_time(doc.created_at),
                "ts": doc.created_at,
            }
        )
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[:limit]


def _dashboard_recommendations() -> list[dict]:
    user = current_user()
    my_categories: set[str] = set()
    for op in Opportunity.query.join(Bookmark, Bookmark.opportunity_id == Opportunity.id).filter(
        Bookmark.user_id == user.id
    ):
        my_categories.update((op.categories or "").split(","))
    my_categories.discard("")

    recs = []
    for kind, icon, endpoint in (("hackathon", "🚀", "hackathons"), ("internship", "💼", "internships")):
        best, best_score, best_match_pct = None, -1.0, 0
        for op in Opportunity.query.filter_by(kind=kind, status="open").all():
            op_cats = set((op.categories or "").split(","))
            op_cats.discard("")
            overlap = len(op_cats & my_categories)
            match_pct = round(100 * overlap / len(op_cats)) if op_cats and overlap else 0

            urgency = 0
            if op.deadline:
                days_left = (op.deadline - date.today()).days
                urgency = max(0, 40 - days_left) if days_left >= 0 else -1000

            score = match_pct * 0.6 + urgency
            if score > best_score:
                best, best_score, best_match_pct = op, score, match_pct

        if best:
            recs.append(
                {
                    "icon": icon,
                    "title": best.title,
                    "reason": "Matches your bookmarked interests" if best_match_pct else "Closing soon",
                    "match_pct": best_match_pct or None,
                    "url": url_for(endpoint),
                }
            )

    latest_item = Item.query.filter_by(status="Available").order_by(Item.created_at.desc()).first()
    if latest_item:
        recs.append(
            {
                "icon": "🔎",
                "title": latest_item.name,
                "reason": "Recently reported in Lost & Found",
                "match_pct": None,
                "url": url_for("lost_found"),
            }
        )
    return recs


@app.route("/")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        hack_stats=_opportunity_stats("hackathon", ("Online",)),
        intern_stats=_opportunity_stats("internship", ("Remote",)),
        doctors_available=Doctor.query.filter_by(available=True).count(),
        lost_items_available=Item.query.filter_by(status="Available").count(),
        activity=_dashboard_activity(),
        recommendations=_dashboard_recommendations(),
        ai_ready=bool(GEMINI_API_KEY),
    )


CAMPUSLY_ASSISTANT_PROMPT = (
    "You are Campusly's in-app assistant, helping a student navigate a campus portal with "
    "four modules: Hackathons (curated hackathon listings), Internships (curated internship "
    "listings), Health / CampusCare (doctor appointments, emergency SOS, wellness check-ins, "
    "blood donor network), and Lost & Found (report or claim items). Answer briefly, 2-4 "
    "sentences, plain text, no markdown. When relevant, name which page to visit. You have no "
    "live access to the database and cannot take actions yourself -- you can only guide the "
    "student to the right page. If asked something unrelated to this app, say so briefly."
)


@app.post("/assistant/ask")
@login_required
def assistant_ask():
    question = (request.form.get("question") or "").strip()[:500]
    if not question:
        return jsonify({"ok": False, "error": "Type a question first."}), 400
    payload = {"contents": [{"parts": [{"text": CAMPUSLY_ASSISTANT_PROMPT + "\n\nStudent's question: " + question}]}]}
    text, error = _gemini_text(payload)
    if error:
        return jsonify({"ok": False, "error": error}), 502
    return jsonify({"ok": True, "answer": text.strip()})


# ---------------------------------------------------------------------------
# Global search -- across opportunities, lost & found items, and doctors.
# ---------------------------------------------------------------------------

@app.route("/search")
@login_required
def search():
    query_text = (request.args.get("q") or "").strip()
    hackathons_r, internships_r, items_r, doctors_r = [], [], [], []

    if query_text:
        pattern = f"%{query_text}%"
        for op in (
            Opportunity.query.filter(db.or_(Opportunity.title.ilike(pattern), Opportunity.organizer.ilike(pattern)))
            .limit(30)
            .all()
        ):
            (hackathons_r if op.kind == "hackathon" else internships_r).append(op)
        items_r = Item.query.filter(db.or_(Item.name.ilike(pattern), Item.location.ilike(pattern))).limit(20).all()
        doctors_r = Doctor.query.filter(Doctor.name.ilike(pattern)).limit(20).all()

    return render_template(
        "search.html",
        query=query_text,
        hackathons=hackathons_r,
        internships=internships_r,
        items=items_r,
        doctors=doctors_r,
        total=len(hackathons_r) + len(internships_r) + len(items_r) + len(doctors_r),
    )


# ---------------------------------------------------------------------------
# Notifications -- a "needs attention" digest built from real pending state
# (claims awaiting review, blood pings, today's appointments, active SOS,
# closing-soon listings). No push delivery, no per-person targeting -- just
# a page that answers "what should I look at right now."
# ---------------------------------------------------------------------------

def _notification_items() -> list[dict]:
    today = date.today()
    items = []

    claimed_items = [i for i in Item.query.filter_by(status="Available").all() if i.claims]
    for i in claimed_items:
        items.append(
            {
                "icon": "🔎",
                "text": f'"{i.name}" has {len(i.claims)} claim(s) awaiting review.',
                "url": url_for("lost_found"),
            }
        )

    pending_pings = BloodPing.query.filter_by(status="pending").count()
    if pending_pings:
        items.append(
            {"icon": "🩸", "text": f"{pending_pings} blood donor ping(s) awaiting a response.", "url": url_for("health")}
        )

    todays_appointments = HealthAppointment.query.filter_by(status="confirmed", appointment_date=today).count()
    if todays_appointments:
        items.append({"icon": "🏥", "text": f"{todays_appointments} appointment(s) today.", "url": url_for("health")})

    active_sos = SOSRequest.query.filter_by(status="active").count()
    if active_sos:
        items.append({"icon": "🚨", "text": f"{active_sos} active SOS alert(s) need attention.", "url": url_for("health")})

    pending_counselor = CounselorRequest.query.filter_by(status="pending").count()
    if pending_counselor:
        items.append(
            {"icon": "🧠", "text": f"{pending_counselor} counselor request(s) pending.", "url": url_for("health")}
        )

    week_out = today + timedelta(days=7)
    closing_soon = Opportunity.query.filter(
        Opportunity.status == "open",
        Opportunity.deadline.isnot(None),
        Opportunity.deadline >= today,
        Opportunity.deadline <= week_out,
    ).count()
    if closing_soon:
        items.append(
            {
                "icon": "⏳",
                "text": f"{closing_soon} hackathon/internship listing(s) closing within a week.",
                "url": url_for("hackathons"),
            }
        )

    return items


@app.route("/notifications")
@login_required
def notifications():
    return render_template("notifications.html", items=_notification_items())


# ---------------------------------------------------------------------------
# Admin analytics -- aggregate counts across every module.
# ---------------------------------------------------------------------------

@app.route("/admin/analytics")
@login_required
def admin_analytics():
    stats = {
        "hackathons_posted": Opportunity.query.filter_by(kind="hackathon").count(),
        "internships_posted": Opportunity.query.filter_by(kind="internship").count(),
        "items_reported": Item.query.count(),
        "items_returned": Item.query.filter_by(status="Returned").count(),
        "claims_submitted": Claim.query.count(),
        "appointments_booked": HealthAppointment.query.count(),
        "sos_total": SOSRequest.query.count(),
        "sos_resolved": SOSRequest.query.filter_by(status="resolved").count(),
        "blood_requests": BloodRequest.query.count(),
        "blood_requests_fulfilled": BloodRequest.query.filter_by(status="fulfilled").count(),
        "mood_checkins": MoodEntry.query.count(),
        "applications_tracked": Application.query.count(),
        "teams_formed": Team.query.count(),
        "users_total": User.query.count(),
    }
    return render_template("admin_analytics.html", stats=stats)


# ---------------------------------------------------------------------------
# Shared Gemini helpers -- every AI feature in this app (Lost & Found photo
# analysis, the two Health features) goes through here, so the retry-on-
# overload behaviour and JSON-extraction only need to be right once.
# ---------------------------------------------------------------------------

def _gemini_text(payload: dict, timeout: int = 30) -> tuple[str | None, str | None]:
    """POST to Gemini and return (reply_text, error_message) -- exactly one is None.

    Retries on HTTP 503 (Gemini's "temporarily overloaded" response) and on
    connection/read timeouts -- both show up often enough in practice that
    surfacing them straight to the user on the first try would be a worse
    experience than one short retry.
    """
    if not GEMINI_API_KEY:
        return None, "AI is not configured. Set GEMINI_API_KEY in .env, then restart the server."

    # None of this app's prompts need multi-step reasoning (classify a photo,
    # write a short answer, a one-line opinion) -- extended "thinking" was
    # measured adding 30+ seconds per call for no quality benefit here.
    payload = dict(payload)
    payload.setdefault("generationConfig", {}).setdefault("thinkingConfig", {}).setdefault("thinkingBudget", 0)

    last_error = "Gemini did not respond."
    attempts = 2
    for attempt in range(attempts):
        try:
            response = requests.post(
                GEMINI_URL,
                headers={"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY},
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = f"Could not reach Gemini: {exc}"
            if attempt == attempts - 1:
                return None, last_error
            time.sleep(1.5)
            continue

        if response.status_code == 200:
            data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"], None
            except (KeyError, IndexError):
                return None, "Gemini's response did not contain any text."

        if response.status_code == 429:
            return None, "The AI assistant has hit its free-tier daily limit. Please try again later."

        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            detail = response.text
        last_error = f"Gemini returned HTTP {response.status_code}: {detail}"

        if response.status_code != 503 or attempt == attempts - 1:
            return None, last_error
        time.sleep(2.5)

    return None, last_error


def _extract_json(text: str) -> dict | None:
    """Gemini sometimes wraps JSON in a ```json fence despite being asked not to."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Lost & Found
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_image(image_bytes: bytes, mime_type: str) -> dict:
    prompt = (
        "You are helping catalogue a lost-and-found item from a photo. "
        "Reply with ONLY a compact JSON object, no markdown fences, no extra text, "
        "matching exactly this shape: "
        '{"name": "short item name", "category": "one of '
        + ", ".join(ITEM_CATEGORIES)
        + '", "description": "one sentence noting color, brand and any distinguishing detail"}'
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
                ]
            }
        ]
    }

    text, error = _gemini_text(payload)
    if error:
        return {"error": error}

    parsed = _extract_json(text)
    if parsed is None:
        return {"error": "Could not parse the AI's response as JSON.", "raw": text}

    if parsed.get("category") not in ITEM_CATEGORIES:
        parsed["category"] = "Other"

    return {"ok": True, "name": parsed.get("name", ""), "category": parsed["category"], "description": parsed.get("description", "")}


def _similar_items(items: list[Item]) -> dict[int, list[Item]]:
    """Same-category items with overlapping words in name/description -- plain
    text overlap, not image or AI matching. Flags possible duplicate reports
    (e.g. two people reporting the same lost phone) without pretending this
    is smarter than it is."""
    available = [i for i in items if i.status == "Available"]
    result: dict[int, list[Item]] = {}
    for a in available:
        a_words = {w for w in (a.name + " " + (a.description or "")).lower().split() if len(w) > 3}
        matches = []
        for b in available:
            if a.id == b.id or a.category != b.category:
                continue
            b_words = {w for w in (b.name + " " + (b.description or "")).lower().split() if len(w) > 3}
            if a_words & b_words:
                matches.append(b)
        if matches:
            result[a.id] = matches[:3]
    return result


@app.route("/lost-found")
@login_required
def lost_found():
    user = current_user()
    query_text = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()

    query = Item.query
    if query_text:
        pattern = f"%{query_text}%"
        query = query.filter(db.or_(Item.name.ilike(pattern), Item.location.ilike(pattern)))
    if category in ITEM_CATEGORIES:
        query = query.filter(Item.category == category)

    items = query.order_by(Item.created_at.desc()).all()

    claim_counts = dict(
        db.session.query(Claim.item_id, db.func.count(Claim.id)).group_by(Claim.item_id).all()
    )
    my_claimed_item_ids = {
        c.item_id for c in Claim.query.filter_by(claimant_id=user.id).with_entities(Claim.item_id).all()
    }
    manageable_item_ids = {
        item.id for item in items if item.reported_by_id == user.id or user.is_admin()
    }

    return render_template(
        "lost_found.html",
        items=items,
        categories=ITEM_CATEGORIES,
        filters={"q": query_text, "category": category},
        ai_ready=bool(GEMINI_API_KEY),
        total_available=Item.query.filter_by(status="Available").count(),
        office=LOST_FOUND_OFFICE,
        claim_counts=claim_counts,
        my_claimed_item_ids=my_claimed_item_ids,
        manageable_item_ids=manageable_item_ids,
        similar_items=_similar_items(items),
    )


@app.post("/lost-found/report")
@login_required
def report_item():
    name = (request.form.get("name") or "").strip()[:120]
    category = (request.form.get("category") or "Other").strip()
    location = (request.form.get("location") or "").strip()[:150]
    description = (request.form.get("description") or "").strip()[:1000]

    if not name:
        return jsonify({"ok": False, "error": "Please give the item a name."}), 400
    if not location:
        return jsonify({"ok": False, "error": "Please say where it was found."}), 400
    if category not in ITEM_CATEGORIES:
        category = "Other"

    filename = None
    file = request.files.get("image")
    if file and file.filename and allowed_file(file.filename):
        extension = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{extension}"
        file.save(os.path.join(UPLOAD_DIR, filename))

    item = Item(
        name=name,
        category=category,
        location=location,
        description=description or None,
        image_filename=filename,
        reported_by_id=current_user().id,
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({"ok": True, "item_id": item.id})


@app.post("/lost-found/claim/<int:item_id>")
@login_required
def claim_item(item_id: int):
    item = db.session.get(Item, item_id)
    if item is None:
        return jsonify({"ok": False, "error": "That item no longer exists."}), 404
    if item.status == "Returned":
        return jsonify({"ok": False, "error": "This item has already been returned to its owner."}), 409

    details = (request.form.get("details") or "").strip()[:500]
    if not details:
        return jsonify({"ok": False, "error": "Describe something that proves it's yours (e.g. \"blue case, cracked corner\")."}), 400

    user = current_user()
    existing = Claim.query.filter_by(item_id=item.id, claimant_id=user.id).first()
    if existing is not None:
        return jsonify({"ok": False, "error": "You've already submitted a claim for this item."}), 409

    claim = Claim(item_id=item.id, claimant_id=user.id, details=details)
    db.session.add(claim)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "message": f"Claim submitted. Collect it from {LOST_FOUND_OFFICE} -- bring ID and be ready to describe it in person.",
        }
    )


@app.get("/lost-found/<int:item_id>/claims")
@login_required
def item_claims(item_id: int):
    item = db.session.get(Item, item_id)
    if item is None:
        abort(404)
    user = current_user()
    if item.reported_by_id != user.id and not user.is_admin():
        abort(403)

    claims = Claim.query.filter_by(item_id=item_id).order_by(Claim.created_at.asc()).all()
    return jsonify(
        {
            "ok": True,
            "claims": [
                {
                    "name": c.claimant.name,
                    "email": c.claimant.email,
                    "details": c.details,
                    "submitted": c.created_at.strftime("%d %b, %H:%M"),
                }
                for c in claims
            ],
        }
    )


@app.post("/lost-found/<int:item_id>/return")
@login_required
def return_item(item_id: int):
    item = db.session.get(Item, item_id)
    if item is None:
        return jsonify({"ok": False, "error": "That item no longer exists."}), 404
    user = current_user()
    if item.reported_by_id != user.id and not user.is_admin():
        abort(403)
    item.status = "Returned"
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/ai/analyze")
@login_required
def ai_analyze():
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Choose a photo first."}), 400

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"ok": False, "error": "That image looks empty."}), 400

    result = analyze_image(image_bytes, file.mimetype or "image/jpeg")
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 502
    return jsonify(result)


# ---------------------------------------------------------------------------
# Hackathons / Internships -- one curated board, two views
#
# hackathon-hub (the sibling project this is modelled on) ingests listings
# from Devpost/MLH automatically and ranks them with a skill-match score.
# This app has no scraper and no student skill profile, so listings are
# posted by hand by admins instead of harvested, and sorting is by deadline/
# reward/recency rather than a computed match score -- everything else
# (category taxonomy, prize/stipend buckets, bookmarks, open/closed status)
# carries over.
# ---------------------------------------------------------------------------

def _opportunity_list(kind: str):
    args = request.args
    query_text = (args.get("q") or "").strip()
    categories = [c for c in args.getlist("category") if c in CATEGORIES]
    mode = (args.get("mode") or "").strip()
    bucket = args.get("prize") if args.get("prize") in PRIZE_BUCKETS else ""
    free_only = args.get("free_only") == "1"
    paid_only = args.get("paid_only") == "1"
    student_only = args.get("student_only") == "1"
    status = args.get("status") if args.get("status") in ("open", "closed", "all") else "open"
    bookmarked_only = args.get("bookmarked_only") == "1"
    sort = args.get("sort") if args.get("sort") in SORT_OPTIONS else "deadline"

    query = Opportunity.query.filter_by(kind=kind)

    if query_text:
        pattern = f"%{query_text}%"
        query = query.filter(
            db.or_(Opportunity.title.ilike(pattern), Opportunity.organizer.ilike(pattern), Opportunity.categories.ilike(pattern))
        )
    for cat in categories:
        query = query.filter(Opportunity.categories.ilike(f"%{cat}%"))
    if mode:
        query = query.filter(Opportunity.mode == mode)
    if bucket:
        lo, hi = PRIZE_BUCKETS[bucket]
        query = query.filter(Opportunity.reward_inr.isnot(None), Opportunity.reward_inr >= lo)
        if hi is not None:
            query = query.filter(Opportunity.reward_inr < hi)
    if free_only:
        query = query.filter(Opportunity.is_free.is_(True))
    if paid_only:
        query = query.filter(Opportunity.is_paid.is_(True))
    if student_only:
        query = query.filter(Opportunity.is_student_only.is_(True))
    if status != "all":
        query = query.filter(Opportunity.status == status)
    if bookmarked_only:
        ids = [b.opportunity_id for b in Bookmark.query.filter_by(user_id=current_user().id).all()]
        query = query.filter(Opportunity.id.in_(ids or [-1]))

    if sort == "reward":
        query = query.order_by(Opportunity.reward_inr.is_(None), Opportunity.reward_inr.desc())
    elif sort == "title":
        query = query.order_by(Opportunity.title.asc())
    elif sort == "recent":
        query = query.order_by(Opportunity.created_at.desc())
    else:
        query = query.order_by(Opportunity.deadline.is_(None), Opportunity.deadline.asc())

    filters = {
        "q": query_text,
        "categories": categories,
        "mode": mode,
        "prize": bucket,
        "free_only": free_only,
        "paid_only": paid_only,
        "student_only": student_only,
        "status": status,
        "bookmarked_only": bookmarked_only,
        "sort": sort,
    }
    return query.all(), filters


def _bookmarked_ids() -> set[int]:
    return {b.opportunity_id for b in Bookmark.query.filter_by(user_id=current_user().id).all()}


def _opportunity_stats(kind: str, online_modes: tuple[str, ...]) -> dict:
    """Headline numbers shown above the board -- always over the whole kind,
    not the currently-applied filters, so the row reads as a stable overview."""
    base = Opportunity.query.filter_by(kind=kind)
    open_base = base.filter(Opportunity.status == "open")
    week_out = date.today() + timedelta(days=7)

    stats = {
        "open": open_base.count(),
        "closing_soon": open_base.filter(
            Opportunity.deadline.isnot(None), Opportunity.deadline >= date.today(), Opportunity.deadline <= week_out
        ).count(),
        "online": open_base.filter(Opportunity.mode.in_(online_modes)).count(),
        "bookmarked": Bookmark.query.join(Opportunity).filter(
            Opportunity.kind == kind, Bookmark.user_id == current_user().id
        ).count(),
    }
    if kind == "hackathon":
        stats["reward_flag"] = open_base.filter(Opportunity.is_free.is_(True)).count()
        stats["reward_label"] = "Free Entry"
    else:
        stats["reward_flag"] = open_base.filter(Opportunity.is_paid.is_(True)).count()
        stats["reward_label"] = "Paid"
    return stats


def _skill_match_scores(opportunities: list[Opportunity]) -> dict[int, int]:
    """Real match % from overlap between the shared profile's skills and each
    opportunity's categories. A skill tag matches a category if it appears
    in (or contains) that category's key or display label -- e.g. a skill
    of "python" matches the "Web" category label loosely, "ai" matches
    "AI / ML". Nothing here is randomised; an opportunity with no overlap
    simply gets no score and no badge."""
    profile = Profile.query.filter_by(user_id=current_user().id).first()
    if not profile or not profile.skill_list():
        return {}
    skill_tokens = {s.lower() for s in profile.skill_list()}
    scores = {}
    for op in opportunities:
        op_cats = op.category_list()
        if not op_cats:
            continue
        matched = 0
        for cat_key in op_cats:
            label = CATEGORIES.get(cat_key, cat_key).lower()
            if any(tok in label or tok == cat_key for tok in skill_tokens):
                matched += 1
        if matched:
            scores[op.id] = round(100 * matched / len(op_cats))
    return scores


@app.route("/hackathons")
@login_required
def hackathons():
    opportunities, filters = _opportunity_list("hackathon")
    teams_by_opportunity: dict[int, list] = {}
    if opportunities:
        for team in Team.query.filter(Team.opportunity_id.in_([op.id for op in opportunities])).all():
            teams_by_opportunity.setdefault(team.opportunity_id, []).append(team)
    return render_template(
        "hackathons.html",
        opportunities=opportunities,
        filters=filters,
        modes=HACKATHON_MODES,
        categories=CATEGORIES,
        prize_buckets=PRIZE_BUCKETS.keys(),
        bookmarked_ids=_bookmarked_ids(),
        stats=_opportunity_stats("hackathon", ("Online",)),
        live_hackathons=fetch_live_hackathons(),
        teams_by_opportunity=teams_by_opportunity,
    )


@app.route("/internships")
@login_required
def internships():
    opportunities, filters = _opportunity_list("internship")
    my_applications = {a.opportunity_id: a.status for a in Application.query.filter_by(user_id=current_user().id).all()}
    return render_template(
        "internships.html",
        opportunities=opportunities,
        filters=filters,
        modes=INTERNSHIP_MODES,
        categories=CATEGORIES,
        prize_buckets=PRIZE_BUCKETS.keys(),
        bookmarked_ids=_bookmarked_ids(),
        stats=_opportunity_stats("internship", ("Remote",)),
        live_internships=fetch_live_internships(),
        match_scores=_skill_match_scores(opportunities),
        my_applications=my_applications,
        application_statuses=APPLICATION_STATUSES,
    )


def _parse_int(raw: str | None) -> int | None:
    raw = (raw or "").strip().replace(",", "")
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


@app.post("/opportunities")
@role_required("admin", "super_admin")
def create_opportunity():
    kind = request.form.get("kind")
    if kind not in ("hackathon", "internship"):
        abort(400)

    title = (request.form.get("title") or "").strip()[:200]
    apply_url = (request.form.get("apply_url") or "").strip()[:500]
    if not title or not apply_url:
        flash("Title and an apply link are required.", "error")
        return redirect(url_for("hackathons" if kind == "hackathon" else "internships"))

    deadline_raw = (request.form.get("deadline") or "").strip()
    deadline = None
    if deadline_raw:
        try:
            deadline = datetime.strptime(deadline_raw, "%Y-%m-%d").date()
        except ValueError:
            deadline = None

    allowed_modes = HACKATHON_MODES if kind == "hackathon" else INTERNSHIP_MODES
    mode = request.form.get("mode") if request.form.get("mode") in allowed_modes else allowed_modes[0]
    categories = ",".join(c for c in request.form.getlist("category") if c in CATEGORIES) or None

    opportunity = Opportunity(
        kind=kind,
        title=title,
        organizer=(request.form.get("organizer") or "").strip()[:150] or None,
        description=(request.form.get("description") or "").strip()[:1000] or None,
        mode=mode,
        location=(request.form.get("location") or "").strip()[:150] or None,
        deadline=deadline,
        reward_text=(request.form.get("reward_text") or "").strip()[:150] or None,
        reward_inr=_parse_int(request.form.get("reward_inr")),
        categories=categories,
        apply_url=apply_url,
        posted_by_id=current_user().id,
        status="open",
    )

    if kind == "hackathon":
        opportunity.is_free = request.form.get("is_free") == "on"
        opportunity.is_student_only = request.form.get("is_student_only") == "on"
        opportunity.team_min = _parse_int(request.form.get("team_min"))
        opportunity.team_max = _parse_int(request.form.get("team_max"))
    else:
        opportunity.is_paid = request.form.get("is_paid") == "on"
        opportunity.duration_text = (request.form.get("duration_text") or "").strip()[:120] or None
        opportunity.eligibility = (request.form.get("eligibility") or "").strip()[:240] or None

    db.session.add(opportunity)
    db.session.commit()
    flash(f"{title} posted.", "success")
    return redirect(url_for("hackathons" if kind == "hackathon" else "internships"))


@app.post("/opportunities/<int:opportunity_id>/delete")
@role_required("admin", "super_admin")
def delete_opportunity(opportunity_id: int):
    opportunity = db.session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return jsonify({"ok": False, "error": "Already gone."}), 404
    Bookmark.query.filter_by(opportunity_id=opportunity_id).delete()
    db.session.delete(opportunity)
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/opportunities/<int:opportunity_id>/status")
@role_required("admin", "super_admin")
def toggle_opportunity_status(opportunity_id: int):
    opportunity = db.session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return jsonify({"ok": False, "error": "Already gone."}), 404
    opportunity.status = "closed" if opportunity.status == "open" else "open"
    db.session.commit()
    return jsonify({"ok": True, "status": opportunity.status})


@app.post("/opportunities/<int:opportunity_id>/bookmark")
@login_required
def toggle_bookmark(opportunity_id: int):
    if db.session.get(Opportunity, opportunity_id) is None:
        return jsonify({"ok": False, "error": "Already gone."}), 404

    existing = Bookmark.query.filter_by(user_id=current_user().id, opportunity_id=opportunity_id).first()
    if existing is not None:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"ok": True, "bookmarked": False})

    db.session.add(Bookmark(user_id=current_user().id, opportunity_id=opportunity_id))
    db.session.commit()
    return jsonify({"ok": True, "bookmarked": True})


# ---------------------------------------------------------------------------
# Internship application pipeline
# ---------------------------------------------------------------------------

@app.post("/opportunities/<int:opportunity_id>/application-status")
@login_required
def set_application_status(opportunity_id: int):
    opportunity = db.session.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.kind != "internship":
        return jsonify({"ok": False, "error": "Not an internship."}), 404

    status = request.form.get("status")
    if status not in APPLICATION_STATUSES:
        return jsonify({"ok": False, "error": "Invalid status."}), 400

    user = current_user()
    application = Application.query.filter_by(opportunity_id=opportunity_id, user_id=user.id).first()
    if application is None:
        application = Application(opportunity_id=opportunity_id, user_id=user.id, status=status)
        db.session.add(application)
    else:
        application.status = status
    db.session.commit()
    return jsonify({"ok": True, "status": status})


@app.post("/opportunities/<int:opportunity_id>/application-status/clear")
@login_required
def clear_application_status(opportunity_id: int):
    Application.query.filter_by(opportunity_id=opportunity_id, user_id=current_user().id).delete()
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Hackathon team formation -- a lightweight roster, not an invite/accept
# flow. There's one shared account (see auth.py), so there's no second
# distinct person to send an invite to; this just lets whoever's forming a
# team list it and what it still needs.
# ---------------------------------------------------------------------------

@app.post("/hackathons/<int:opportunity_id>/teams")
@login_required
def create_team(opportunity_id: int):
    opportunity = db.session.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.kind != "hackathon":
        return jsonify({"ok": False, "error": "Not a hackathon."}), 404

    name = (request.form.get("name") or "").strip()[:120]
    if not name:
        return jsonify({"ok": False, "error": "Give the team a name."}), 400
    looking_for = (request.form.get("looking_for") or "").strip()[:300]

    team = Team(opportunity_id=opportunity_id, name=name, looking_for=looking_for or None, created_by_id=current_user().id)
    db.session.add(team)
    db.session.flush()

    member_lines = [line.strip() for line in (request.form.get("members") or "").splitlines() if line.strip()]
    for line in member_lines[:20]:
        if "-" in line:
            member_name, role = line.split("-", 1)
        else:
            member_name, role = line, ""
        db.session.add(TeamMember(team_id=team.id, name=member_name.strip()[:120], role=role.strip()[:80] or None))

    db.session.commit()
    return jsonify({"ok": True, "team_id": team.id})


@app.post("/hackathons/teams/<int:team_id>/delete")
@login_required
def delete_team(team_id: int):
    team = db.session.get(Team, team_id)
    if team is None:
        return jsonify({"ok": False, "error": "Already gone."}), 404
    db.session.delete(team)
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Shared profile -- skills + resume, used for the internship match score
# and AI resume feedback.
# ---------------------------------------------------------------------------

def _get_or_create_profile() -> Profile:
    user = current_user()
    profile = Profile.query.filter_by(user_id=user.id).first()
    if profile is None:
        profile = Profile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()
    return profile


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    prof = _get_or_create_profile()
    if request.method == "POST":
        prof.skills = (request.form.get("skills") or "").strip()[:500]
        prof.resume_text = (request.form.get("resume_text") or "").strip()[:8000]
        db.session.commit()
        flash("Profile saved.", "success")
        return redirect(url_for("profile"))

    my_applications = (
        Application.query.filter_by(user_id=current_user().id).join(Opportunity).order_by(Application.updated_at.desc()).all()
    )
    return render_template(
        "profile.html",
        profile=prof,
        ai_ready=bool(GEMINI_API_KEY),
        my_applications=my_applications,
        internships=Opportunity.query.filter_by(kind="internship", status="open").order_by(Opportunity.title.asc()).all(),
    )


@app.post("/profile/resume-feedback")
@login_required
def resume_feedback():
    prof = _get_or_create_profile()
    if not prof.resume_text:
        return jsonify({"ok": False, "error": "Paste your resume text first."}), 400

    target_id = request.form.get("opportunity_id", type=int)
    target = db.session.get(Opportunity, target_id) if target_id else None

    prompt = (
        "You are a concise career advisor reviewing a student's resume (plain text, may be messy). "
        "Give: (1) 2-3 sentences of overall feedback, (2) a short bullet list of specific missing skills "
        "or sections, (3) one concrete improvement suggestion. Keep the whole reply under 150 words, "
        "plain text, no markdown headers.\n\n"
    )
    if target is not None:
        prompt += f'The student is targeting this internship: "{target.title}" at {target.organizer or "the organization"}. '
        if target.category_labels():
            prompt += f"Its listed categories: {', '.join(target.category_labels())}. "
        prompt += "Weigh your feedback toward what this specific role needs.\n\n"

    prompt += "Resume:\n" + prof.resume_text[:6000]

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    text, error = _gemini_text(payload)
    if error:
        return jsonify({"ok": False, "error": error}), 502
    return jsonify({"ok": True, "feedback": text.strip()})


# ---------------------------------------------------------------------------
# Health -- a disease/symptom Q&A assistant, and a clinic verifier that
# cross-checks a clinic name against real Google Search results before
# trusting any phone number it gives you.
# ---------------------------------------------------------------------------

HEALTH_SYSTEM_PROMPT = (
    "You are a cautious health-information assistant inside a college portal. "
    "A student has asked a question about symptoms or a disease. Answer in plain, "
    "reassuring language, under 180 words. "
    "Never give a specific diagnosis and never give medication names or dosages. "
    "If the question describes a possible emergency (severe chest pain, trouble "
    "breathing, signs of stroke, heavy bleeding, suicidal thoughts, or similar), "
    "your FIRST sentence must tell them to seek emergency care immediately. "
    "Always end with a short reminder to see a qualified doctor for diagnosis and "
    "treatment -- this is general information, not medical advice."
)


def ask_health_question(question: str) -> dict:
    payload = {"contents": [{"parts": [{"text": HEALTH_SYSTEM_PROMPT + "\n\nStudent's question: " + question}]}]}
    text, error = _gemini_text(payload)
    if error:
        return {"error": error}
    return {"ok": True, "answer": text.strip()}


def extract_clinic_from_image(image_bytes: bytes, mime_type: str) -> dict:
    """Read a clinic name (and any phone number) off a signboard/letterhead photo."""
    prompt = (
        "This image may show a clinic or hospital signboard, letterhead or pamphlet. "
        "Reply with ONLY a compact JSON object, no markdown, no extra text: "
        '{"clinic_name": "name found, or empty string", "phone_on_image": "phone number found, or null"}'
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
                ]
            }
        ]
    }
    text, error = _gemini_text(payload)
    if error:
        return {"clinic_name": "", "phone_on_image": None}
    return _extract_json(text) or {"clinic_name": "", "phone_on_image": None}


def verify_clinic(name: str, location: str) -> dict:
    """Give an honest, free second opinion on a clinic name.

    There is no live Google Search here -- that needs Gemini's search-grounding
    tool, which is billed and this project runs on the free tier. So instead of
    pretending to "verify" a phone number, this asks Gemini what it already
    knows from training (which can be wrong or outdated) and, more usefully,
    gives the student concrete steps to check the clinic themselves. Never
    silently claim a live verification that isn't happening.
    """
    query_subject = f"{name}, {location}" if location else name
    prompt = (
        "A student wants a second opinion on whether a clinic/hospital is likely "
        f'legitimate: "{query_subject}". You have NO live internet access -- do not '
        "claim to have looked anything up. Using only general knowledge: (1) say "
        "whether you recognise this as an established, known clinic/hospital name "
        "or chain, or whether it's unfamiliar to you; (2) note anything about the "
        "name itself that reads as a red flag (generic bait names, no clear "
        "specialty, pressure-selling language) versus reassuring (well-known "
        "hospital group, recognisable brand). "
        "Reply with ONLY a compact JSON object, no markdown, no extra text: "
        '{"recognised": true or false, "note": "two or three sentences with your '
        'honest, hedged opinion -- make clear this is not a live lookup"}'
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    text, error = _gemini_text(payload)
    if error:
        return {"error": error}

    parsed = _extract_json(text)
    if parsed is None:
        return {"error": "Could not parse the AI's response as JSON.", "raw": text}

    return {
        "ok": True,
        "clinic_name": name,
        "recognised": bool(parsed.get("recognised")),
        "note": parsed.get("note", ""),
    }


@app.route("/health")
@login_required
def health():
    user = current_user()
    today = date.today()

    doctors = Doctor.query.order_by(Doctor.available.desc(), Doctor.name.asc()).all()
    todays_queue = HealthAppointment.query.filter_by(appointment_date=today, status="confirmed").count()

    active_sos = (
        SOSRequest.query.filter_by(status="active").order_by(SOSRequest.created_at.desc()).all()
        if user.is_admin()
        else []
    )
    my_sos_active = SOSRequest.query.filter_by(user_id=user.id, status="active").first() is not None

    my_mood_today = MoodEntry.query.filter_by(user_id=user.id, entry_date=today).first()
    since = datetime.utcnow() - timedelta(days=7)
    recent_moods = MoodEntry.query.filter(MoodEntry.created_at >= since).all()
    mood_weight = {"great": 100, "good": 75, "okay": 50, "low": 25, "stressed": 10}
    wellness_score = (
        round(sum(mood_weight[m.mood] for m in recent_moods) / len(recent_moods))
        if recent_moods
        else None
    )

    my_donor_profile = BloodDonor.query.filter_by(user_id=user.id).first()
    open_blood_requests = (
        BloodRequest.query.filter(
            db.or_(BloodRequest.status == "open", BloodRequest.requested_by_id == user.id)
        )
        .order_by(BloodRequest.created_at.desc())
        .limit(10)
        .all()
    )
    my_pending_pings = (
        BloodPing.query.join(BloodDonor)
        .filter(BloodDonor.user_id == user.id, BloodPing.status == "pending")
        .all()
        if my_donor_profile
        else []
    )

    my_upcoming_appointments = (
        HealthAppointment.query.filter(
            HealthAppointment.user_id == user.id,
            HealthAppointment.status == "confirmed",
            HealthAppointment.appointment_date >= today,
        )
        .order_by(HealthAppointment.appointment_date.asc())
        .all()
    )

    stats_served = (
        MoodEntry.query.count()
        + HealthAppointment.query.count()
        + SOSRequest.query.filter_by(status="resolved").count()
    )

    medicine_reminders = (
        MedicineReminder.query.filter_by(user_id=user.id).order_by(MedicineReminder.time_of_day.asc()).all()
    )

    return render_template(
        "health.html",
        ai_ready=bool(GEMINI_API_KEY),
        doctors=doctors,
        medicine_reminders=medicine_reminders,
        todays_queue=todays_queue,
        active_sos=active_sos,
        my_sos_active=my_sos_active,
        sos_types=SOS_TYPES,
        moods=MOODS,
        mood_emoji=MOOD_EMOJI,
        my_mood_today=my_mood_today,
        wellness_score=wellness_score,
        recent_mood_count=len(recent_moods),
        my_donor_profile=my_donor_profile,
        blood_groups=BLOOD_GROUPS,
        open_blood_requests=open_blood_requests,
        my_pending_pings=my_pending_pings,
        appointment_slots=APPOINTMENT_SLOTS,
        my_upcoming_appointments=my_upcoming_appointments,
        stats_served=stats_served,
        health_center={
            "name": HEALTH_CENTER_NAME,
            "phone": HEALTH_CENTER_PHONE,
            "timings": HEALTH_CENTER_TIMINGS,
            "location": HEALTH_CENTER_LOCATION,
        },
        today=today,
    )


# --- Doctors (admin-managed) -----------------------------------------------

@app.post("/health/doctors")
@role_required("admin", "super_admin")
def add_doctor():
    name = (request.form.get("name") or "").strip()[:120]
    specialty = (request.form.get("specialty") or "").strip()[:120]
    if not name:
        flash("Enter a doctor's name.", "error")
        return redirect(url_for("health"))
    db.session.add(Doctor(name=name, specialty=specialty or None, available=True))
    db.session.commit()
    flash(f"Dr. {name} added.", "success")
    return redirect(url_for("health"))


@app.post("/health/doctors/<int:doctor_id>/toggle")
@role_required("admin", "super_admin")
def toggle_doctor(doctor_id: int):
    doctor = db.session.get(Doctor, doctor_id)
    if doctor is None:
        return jsonify({"ok": False, "error": "Not found."}), 404
    doctor.available = not doctor.available
    db.session.commit()
    return jsonify({"ok": True, "available": doctor.available})


# --- Medicine reminders -------------------------------------------------------
# Plain reminders only -- never a dosing recommendation. Firing them is a
# client-side setInterval check against time_of_day while the tab is open
# (see health.js); there's no server push, so a reminder only fires while
# Campusly is open somewhere.

@app.post("/health/medicine")
@login_required
def add_medicine_reminder():
    name = (request.form.get("medicine_name") or "").strip()[:120]
    dosage = (request.form.get("dosage") or "").strip()[:80]
    time_of_day = (request.form.get("time_of_day") or "").strip()

    if not name:
        return jsonify({"ok": False, "error": "Name the medicine."}), 400
    try:
        hh, mm = time_of_day.split(":")
        if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError
    except (ValueError, AttributeError):
        return jsonify({"ok": False, "error": "Choose a valid time."}), 400

    reminder = MedicineReminder(
        user_id=current_user().id, medicine_name=name, dosage=dosage or None, time_of_day=time_of_day
    )
    db.session.add(reminder)
    db.session.commit()
    return jsonify(
        {
            "ok": True,
            "reminder": {
                "id": reminder.id,
                "medicine_name": reminder.medicine_name,
                "dosage": reminder.dosage,
                "time_of_day": reminder.time_of_day,
                "active": reminder.active,
            },
        }
    )


@app.post("/health/medicine/<int:reminder_id>/toggle")
@login_required
def toggle_medicine_reminder(reminder_id: int):
    reminder = db.session.get(MedicineReminder, reminder_id)
    if reminder is None or reminder.user_id != current_user().id:
        return jsonify({"ok": False, "error": "Not found."}), 404
    reminder.active = not reminder.active
    db.session.commit()
    return jsonify({"ok": True, "active": reminder.active})


@app.post("/health/medicine/<int:reminder_id>/delete")
@login_required
def delete_medicine_reminder(reminder_id: int):
    reminder = db.session.get(MedicineReminder, reminder_id)
    if reminder is None or reminder.user_id != current_user().id:
        return jsonify({"ok": False, "error": "Not found."}), 404
    db.session.delete(reminder)
    db.session.commit()
    return jsonify({"ok": True})


# --- Emergency SOS -----------------------------------------------------------

@app.post("/health/sos")
@login_required
def create_sos():
    emergency_type = request.form.get("emergency_type")
    location = (request.form.get("location") or "").strip()[:200]
    if emergency_type not in SOS_TYPES:
        return jsonify({"ok": False, "error": "Choose an emergency type."}), 400
    if not location:
        return jsonify({"ok": False, "error": "Enter your location."}), 400

    sos = SOSRequest(user_id=current_user().id, emergency_type=emergency_type, location=location)
    db.session.add(sos)
    db.session.commit()
    return jsonify({"ok": True, "id": sos.id})


@app.post("/health/sos/<int:sos_id>/resolve")
@role_required("admin", "super_admin")
def resolve_sos(sos_id: int):
    sos = db.session.get(SOSRequest, sos_id)
    if sos is None:
        return jsonify({"ok": False, "error": "Not found."}), 404
    sos.status = "resolved"
    sos.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


# --- Mental wellness ---------------------------------------------------------

@app.post("/health/mood")
@login_required
def submit_mood():
    mood = request.form.get("mood")
    if mood not in MOODS:
        return jsonify({"ok": False, "error": "Pick one of the moods."}), 400

    today = date.today()
    entry = MoodEntry.query.filter_by(user_id=current_user().id, entry_date=today).first()
    if entry:
        entry.mood = mood
    else:
        db.session.add(MoodEntry(user_id=current_user().id, mood=mood, entry_date=today))
    db.session.commit()
    return jsonify({"ok": True, "mood": mood})


@app.post("/health/counselor-request")
@login_required
def request_counselor():
    note = (request.form.get("note") or "").strip()[:1000]
    db.session.add(CounselorRequest(user_id=current_user().id, note=note or None))
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/health/support")
@login_required
def submit_support_message():
    """Deliberately doesn't record who sent this -- see SupportMessage."""
    message = (request.form.get("message") or "").strip()[:1000]
    if not message:
        return jsonify({"ok": False, "error": "Write something first."}), 400
    db.session.add(SupportMessage(message=message))
    db.session.commit()
    return jsonify({"ok": True})


# --- Blood donor network ------------------------------------------------------

@app.post("/health/blood/register")
@login_required
def register_donor():
    blood_group = request.form.get("blood_group")
    if blood_group not in BLOOD_GROUPS:
        return jsonify({"ok": False, "error": "Choose a valid blood group."}), 400

    location = (request.form.get("location") or "").strip()[:150]
    phone = (request.form.get("phone") or "").strip()[:32]
    available = request.form.get("available") == "on"

    profile = BloodDonor.query.filter_by(user_id=current_user().id).first()
    if profile is None:
        profile = BloodDonor(user_id=current_user().id)
        db.session.add(profile)
    profile.blood_group = blood_group
    profile.location = location or None
    profile.phone = phone or None
    profile.available = available
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/health/blood/request")
@login_required
def create_blood_request():
    blood_group = request.form.get("blood_group")
    if blood_group not in BLOOD_GROUPS:
        return jsonify({"ok": False, "error": "Choose a valid blood group."}), 400
    note = (request.form.get("note") or "").strip()[:300]

    req = BloodRequest(requested_by_id=current_user().id, blood_group=blood_group, note=note or None)
    db.session.add(req)
    db.session.flush()

    matches = BloodDonor.query.filter_by(blood_group=blood_group, available=True).filter(
        BloodDonor.user_id != current_user().id
    ).all()
    for donor in matches:
        db.session.add(BloodPing(request_id=req.id, donor_id=donor.id))
    db.session.commit()
    return jsonify({"ok": True, "id": req.id, "notified": len(matches)})


@app.post("/health/blood/ping/<int:ping_id>/respond")
@login_required
def respond_to_blood_ping(ping_id: int):
    ping = db.session.get(BloodPing, ping_id)
    if ping is None:
        return jsonify({"ok": False, "error": "Not found."}), 404
    if ping.donor.user_id != current_user().id:
        abort(403)

    decision = request.form.get("decision")
    if decision not in ("accepted", "declined"):
        return jsonify({"ok": False, "error": "Invalid decision."}), 400

    ping.status = decision
    if decision == "accepted":
        ping.request.status = "fulfilled"
    db.session.commit()
    return jsonify({"ok": True})


@app.get("/health/blood/request/<int:request_id>/responses")
@login_required
def blood_request_responses(request_id: int):
    """Contact details are only ever returned here, to the student who made
    the request, and only for donors who already accepted."""
    req = db.session.get(BloodRequest, request_id)
    if req is None or req.requested_by_id != current_user().id:
        abort(403)

    accepted = BloodPing.query.filter_by(request_id=request_id, status="accepted").all()
    return jsonify(
        {
            "ok": True,
            "donors": [
                {"name": p.donor.user.name, "phone": p.donor.phone, "location": p.donor.location}
                for p in accepted
            ],
        }
    )


# --- Doctor appointments -------------------------------------------------------

@app.post("/health/appointments")
@login_required
def book_appointment():
    doctor_id = request.form.get("doctor_id", type=int)
    date_raw = (request.form.get("date") or "").strip()
    time_slot = request.form.get("time_slot")

    doctor = db.session.get(Doctor, doctor_id) if doctor_id else None
    if doctor is None:
        return jsonify({"ok": False, "error": "Choose a doctor."}), 400
    if time_slot not in APPOINTMENT_SLOTS:
        return jsonify({"ok": False, "error": "Choose a time slot."}), 400
    try:
        appointment_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Choose a valid date."}), 400
    if appointment_date < date.today():
        return jsonify({"ok": False, "error": "Choose a date that hasn't passed."}), 400

    clash = HealthAppointment.query.filter_by(
        doctor_id=doctor.id, appointment_date=appointment_date, time_slot=time_slot, status="confirmed"
    ).first()
    if clash:
        return jsonify({"ok": False, "error": "That slot is already booked. Pick another time."}), 409

    appt = HealthAppointment(
        user_id=current_user().id, doctor_id=doctor.id, appointment_date=appointment_date, time_slot=time_slot
    )
    db.session.add(appt)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "doctor_name": doctor.name,
            "date": appointment_date.strftime("%d %b %Y"),
            "time_slot": time_slot,
            "location": HEALTH_CENTER_NAME,
        }
    )


@app.post("/health/ask")
@login_required
def health_ask():
    question = (request.form.get("question") or "").strip()[:1000]
    if not question:
        return jsonify({"ok": False, "error": "Type a question first."}), 400
    result = ask_health_question(question)
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 502
    return jsonify(result)


@app.post("/health/verify-clinic")
@login_required
def health_verify_clinic():
    name = (request.form.get("name") or "").strip()[:200]
    location = (request.form.get("location") or "").strip()[:150]

    file = request.files.get("image")
    if file and file.filename:
        image_bytes = file.read()
        if image_bytes:
            extracted = extract_clinic_from_image(image_bytes, file.mimetype or "image/jpeg")
            if not name and extracted.get("clinic_name"):
                name = extracted["clinic_name"][:200]

    if not name:
        return jsonify({"ok": False, "error": "Enter a clinic name, or upload a clearer photo."}), 400

    result = verify_clinic(name, location)
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 502
    return jsonify(result)


# ---------------------------------------------------------------------------
# Super-admin: manage user roles
# ---------------------------------------------------------------------------

@app.route("/admin/users")
@role_required("super_admin")
def manage_users():
    users = User.query.order_by(User.created_at.asc()).all()
    return render_template("admin_users.html", users=users)


@app.post("/admin/users/<int:user_id>/role")
@role_required("super_admin")
def change_user_role(user_id: int):
    target = db.session.get(User, user_id)
    if target is None:
        abort(404)
    if target.role == "super_admin":
        flash("Super admins can't be changed from here.", "error")
        return redirect(url_for("manage_users"))

    new_role = request.form.get("role")
    if new_role not in ("student", "admin"):
        abort(400)

    target.role = new_role
    db.session.commit()
    flash(f"{target.name} is now {new_role.replace('_', ' ')}.", "success")
    return redirect(url_for("manage_users"))


# ---------------------------------------------------------------------------
# Startup: create tables and seed the first super admin
# ---------------------------------------------------------------------------

def _seed_super_admin() -> None:
    if User.query.filter_by(role="super_admin").first() is not None:
        return

    email = os.environ.get("SUPER_ADMIN_EMAIL", "admin@mvv.local").strip().lower()
    password = os.environ.get("SUPER_ADMIN_PASSWORD", "").strip()
    generated = False
    if not password:
        password = secrets.token_urlsafe(9)
        generated = True

    existing = User.query.filter_by(email=email).first()
    if existing is not None:
        existing.role = "super_admin"
        db.session.commit()
        app.logger.warning("Promoted existing user %s to super_admin.", email)
        return

    admin = User(name="Super Admin", email=email, password_hash=hash_password(password), role="super_admin")
    db.session.add(admin)
    db.session.commit()

    print("=" * 70)
    print(" First run: created the super admin account")
    print(f"   email:    {email}")
    if generated:
        print(f"   password: {password}   (auto-generated -- save this now)")
    else:
        print("   password: (from SUPER_ADMIN_PASSWORD in .env)")
    print(" Set SUPER_ADMIN_EMAIL / SUPER_ADMIN_PASSWORD in .env to control this.")
    print("=" * 70)


with app.app_context():
    db.create_all()
    _seed_super_admin()


if __name__ == "__main__":
    app.run(port=5052, debug=True)
