# Campusly

A small campus portal: Hackathons, Internships, a Health placeholder, and a
Lost & Found board, behind student / admin / super-admin login.

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
  Lost & Found items, and apply to hackathons/internships (external links).
- **admin** -- everything a student can, plus posting and removing
  hackathon/internship listings.
- **super_admin** -- everything an admin can, plus `/admin/users` to promote
  a student to admin (or demote them back).

There is exactly one super admin, seeded from `SUPER_ADMIN_EMAIL` /
`SUPER_ADMIN_PASSWORD` in `.env` on first run. There is no signup path to
admin or super_admin -- a super admin has to promote someone from the Users
page.

## AI photo analysis

The Lost & Found report form has an "Analyze with AI" button: pick a photo,
and Gemini suggests the item's name, category and description. Needs
`GEMINI_API_KEY` set in `.env` (get one at
https://aistudio.google.com/apikey) -- without it the button is replaced
with a note and the rest of the app works normally.

## Structure

```
app.py                   routes, Gemini call, super-admin seeding
models.py                User, Item (Lost & Found), Opportunity (Hackathons/Internships)
auth.py                  password hashing, session helpers, login_required / role_required
extensions.py             shared db instance
templates/
  base.html               nav + flash messages, extended by every page
  login.html, signup.html
  dashboard.html          4 module tiles
  lost_found.html
  hackathons.html, internships.html, _opportunity_macros.html
  health.html             placeholder
  admin_users.html        super-admin only
static/
  style.css               single stylesheet, warm/coral palette
  csrf.js                 exposes the CSRF token to the other scripts
  lost_found.js, opportunities.js
```

One Flask app, one `Opportunity` table shared by Hackathons and Internships
(distinguished by a `kind` column) -- this is a curated board admins post to
by hand, not a scraper/aggregator.
