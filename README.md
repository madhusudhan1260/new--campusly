# Campusly

A small campus portal: Hackathons, Internships, Health, and a Lost & Found
board, behind student / admin / super-admin login.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in GEMINI_API_KEY and SUPER_ADMIN_PASSWORD
python app.py
```

Runs on **http://127.0.0.1:5052**.

The database (`mvv.db`) and the super-admin account are created automatically
on first run.

## Roles

- **student** -- signs up at `/signup`. Can browse everything, report/claim
  Lost & Found items, bookmark and apply to hackathons/internships (external
  links), and use both Health features.
- **admin** -- everything a student can, plus posting, closing/reopening and
  removing hackathon/internship listings.
- **super_admin** -- everything an admin can, plus `/admin/users` to promote
  a student to admin (or demote them back).

There is exactly one super admin, seeded from `SUPER_ADMIN_EMAIL` /
`SUPER_ADMIN_PASSWORD` in `.env` on first run. There is no signup path to
admin or super_admin -- a super admin has to promote someone from the Users
page.

## Modules

**Hackathons / Internships** -- one curated board (admins post by hand, no
scraper), shared category taxonomy across both, deadline urgency badges,
prize/stipend buckets for filtering, bookmarks, and open/closed status.

**Health** -- two Gemini-backed features, both intentionally honest about
what they can and can't do:
- A symptom/disease Q&A assistant that always defers to a real doctor and
  leads with emergency guidance when a question sounds like one.
- A clinic "second opinion" tool. It has **no live internet access** (that
  needs Gemini's paid Google Search grounding, which this project doesn't
  use), so it never claims to verify a phone number -- it gives its general
  opinion on the name and points the student at a concrete self-verification
  checklist instead.

**Lost & Found** -- report/claim found items, with an optional "Analyze with
AI" button that has Gemini suggest a name/category/description from a photo.

## AI configuration

All three AI features (Lost & Found photo analysis, Health Q&A, clinic
opinion) share one Gemini key and one retry-aware helper (`_gemini_text` in
`app.py`) that disables "thinking" mode -- these are all short, simple tasks
that don't need it, and it cuts response time from 30+ seconds to a few --
and retries once on a timeout or the transient 503 "model overloaded"
response. Set `GEMINI_API_KEY` in `.env` (get one at
https://aistudio.google.com/apikey); without it, each AI button is disabled
with a note, and the rest of the app works normally.

## Structure

```
app.py                   routes, Gemini helpers, super-admin seeding
models.py                User, Item (Lost & Found), Opportunity, Bookmark
auth.py                  password hashing, session helpers, login_required / role_required
extensions.py             shared db instance
templates/
  base.html               nav + flash messages + animated background, extended by every page
  login.html, signup.html
  dashboard.html          4 module tiles
  lost_found.html
  hackathons.html, internships.html, _opportunity_macros.html
  health.html             Q&A + clinic opinion
  admin_users.html        super-admin only
static/
  style.css               dark theme, Inter font, type scale, animations
  csrf.js                 exposes the CSRF token to the other scripts
  lost_found.js, opportunities.js, health.js
```

One Flask app, one `Opportunity` table shared by Hackathons and Internships
(distinguished by a `kind` column) -- this is a curated board admins post to
by hand, not a scraper/aggregator.
