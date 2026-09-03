"""Database models: users, lost-and-found items, and the opportunity board
shared by Hackathons and Internships."""

from __future__ import annotations

from datetime import datetime

from extensions import db

ROLES = ("student", "admin", "super_admin")
OPPORTUNITY_KINDS = ("hackathon", "internship")

# Same taxonomy as the hackathon-hub classifier's CATEGORIES keys, so the
# category a listing gets tagged with means the same thing a user would
# expect from that project -- just applied by whoever posts the listing here
# instead of an automatic classifier.
CATEGORIES = {
    "ai-ml": "AI / ML",
    "web": "Web",
    "cybersecurity": "Cybersecurity",
    "cloud": "Cloud",
    "blockchain": "Blockchain",
    "mobile": "Mobile",
    "data": "Data",
    "iot-hardware": "IoT / Hardware",
    "fintech": "Fintech",
    "healthtech": "Healthtech",
    "gamedev": "Game Dev",
    "design": "Design",
    "sustainability": "Sustainability",
    "open-source": "Open Source",
}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def is_admin(self) -> bool:
        return self.role in ("admin", "super_admin")

    def is_super_admin(self) -> bool:
        return self.role == "super_admin"


class Item(db.Model):
    """A found item logged on the Lost & Found board."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Other")
    location = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Available")
    reported_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    reported_by = db.relationship("User", foreign_keys=[reported_by_id])


class Claim(db.Model):
    """A claim of ownership on a found item.

    More than one person can claim the same item -- proving ownership (e.g.
    describing a mark only the real owner would know) happens in person when
    they collect it, not in the app. This just collects everyone's claim
    details so whoever hands the item over has something to check against.
    """

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False, index=True)
    claimant_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    details = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    item = db.relationship("Item", foreign_keys=[item_id], backref=db.backref("claims", order_by="Claim.created_at"))
    claimant = db.relationship("User", foreign_keys=[claimant_id])


class Opportunity(db.Model):
    """A hackathon or internship posted to the curated board.

    One table for both, distinguished by `kind` -- almost every field is
    meaningful for both (title, organizer, deadline, mode, categories, a
    numeric amount for sorting/bucketing, an external apply link). A few
    fields only make sense for one kind (team size for hackathons; duration
    and eligibility for internships) and are simply left null on the other.
    """

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    organizer = db.Column(db.String(150), nullable=True)
    description = db.Column(db.Text, nullable=True)
    mode = db.Column(db.String(20), nullable=False, default="Online")
    location = db.Column(db.String(150), nullable=True)
    deadline = db.Column(db.Date, nullable=True, index=True)

    # Numeric so it can be sorted and bucketed (0-10k / 10k-1L / 1L+), same
    # buckets hackathon-hub uses. `reward_text` is what's actually shown
    # ("₹50,000", "Certificate + swag") since not every reward is a clean
    # number.
    reward_text = db.Column(db.String(150), nullable=True)
    reward_inr = db.Column(db.Integer, nullable=True, index=True)

    categories = db.Column(db.String(300), nullable=True)  # comma-separated CATEGORIES keys

    # Hackathon-only.
    is_free = db.Column(db.Boolean, nullable=True)
    is_student_only = db.Column(db.Boolean, nullable=True)
    team_min = db.Column(db.Integer, nullable=True)
    team_max = db.Column(db.Integer, nullable=True)

    # Internship-only.
    is_paid = db.Column(db.Boolean, nullable=True)
    duration_text = db.Column(db.String(120), nullable=True)
    eligibility = db.Column(db.String(240), nullable=True)
    # Comma-separated specific skills (e.g. "Python, Django, REST API") --
    # optional, admin-entered. Powers the Skill Gap checklist; without it,
    # matching falls back to the broader category overlap only.
    required_skills = db.Column(db.String(300), nullable=True)

    status = db.Column(db.String(10), nullable=False, default="open")  # open|closed
    apply_url = db.Column(db.String(500), nullable=False)
    posted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    posted_by = db.relationship("User", foreign_keys=[posted_by_id])

    def category_list(self) -> list[str]:
        if not self.categories:
            return []
        return [c.strip() for c in self.categories.split(",") if c.strip()]

    def category_labels(self) -> list[str]:
        return [CATEGORIES.get(c, c) for c in self.category_list()]

    def required_skill_list(self) -> list[str]:
        if not self.required_skills:
            return []
        return [s.strip() for s in self.required_skills.split(",") if s.strip()]


class Bookmark(db.Model):
    """A student saving a hackathon/internship for later."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "opportunity_id", name="uq_bookmark_user_opportunity"),)


class Profile(db.Model):
    """Skills + resume used to score internship matches.

    There's one shared account now (see auth.py), so there's one profile --
    skills and resume aren't per-visitor, they're the workspace's own.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    skills = db.Column(db.Text, nullable=True)  # comma-separated free text tags
    resume_text = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    def skill_list(self) -> list[str]:
        if not self.skills:
            return []
        return [s.strip() for s in self.skills.split(",") if s.strip()]


APPLICATION_STATUSES = ("Applied", "Shortlisted", "Interview", "Selected", "Rejected")


class Application(db.Model):
    """Tracks progress through the hiring pipeline for one internship."""

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Applied")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("opportunity_id", "user_id", name="uq_application_opp_user"),)

    opportunity = db.relationship("Opportunity", foreign_keys=[opportunity_id])


class Team(db.Model):
    """A hackathon team roster.

    With one shared account there's no real invite/accept flow between
    distinct people, so this is a lightweight roster instead: whoever's
    forming the team lists teammate names/roles as plain text. Simple, but
    honest about what's actually possible without individual accounts.
    """

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    looking_for = db.Column(db.String(300), nullable=True)  # comma-separated roles, e.g. "ML Engineer, Frontend Developer"
    max_members = db.Column(db.Integer, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    opportunity = db.relationship("Opportunity", foreign_keys=[opportunity_id])
    members = db.relationship("TeamMember", backref="team", order_by="TeamMember.id", cascade="all, delete-orphan")


class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(80), nullable=True)


# ---------------------------------------------------------------------------
# CampusCare -- Health Center, SOS, Wellness, Blood Network, Appointments.
# ---------------------------------------------------------------------------

BLOOD_GROUPS = ("O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-")
SOS_TYPES = ("Medical emergency", "Injury", "Accident", "Other")
MOODS = ("great", "good", "okay", "low", "stressed")
MOOD_EMOJI = {"great": "😊", "good": "🙂", "okay": "😐", "low": "😔", "stressed": "😣"}


class Doctor(db.Model):
    """A campus health center doctor. Admin-managed, not self-service."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialty = db.Column(db.String(120), nullable=True)
    available = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class HealthAppointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctor.id"), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False, index=True)
    time_slot = db.Column(db.String(20), nullable=False)  # e.g. "10:30 AM"
    status = db.Column(db.String(20), nullable=False, default="confirmed")  # confirmed|cancelled
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    doctor = db.relationship("Doctor", foreign_keys=[doctor_id])


class MedicineReminder(db.Model):
    """A recurring reminder to take a medicine -- a plain reminder, never a
    prescription or dosing recommendation. The browser checks these while
    the tab is open and fires a Notification; there's no server-side push,
    so a reminder only fires while Campusly is open somewhere."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    medicine_name = db.Column(db.String(120), nullable=False)
    dosage = db.Column(db.String(80), nullable=True)
    time_of_day = db.Column(db.String(5), nullable=False)  # "HH:MM", 24h
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])


class SOSRequest(db.Model):
    """A campus emergency alert. Shown live to admins so someone can act on it."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    emergency_type = db.Column(db.String(30), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)  # active|resolved
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])


class MoodEntry(db.Model):
    """One check-in per student per day."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    mood = db.Column(db.String(20), nullable=False)
    entry_date = db.Column(db.Date, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "entry_date", name="uq_mood_user_day"),)


class CounselorRequest(db.Model):
    """A named request for a counselor session -- unlike Anonymous Support,
    the counselor needs to know who to schedule with."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending|contacted
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])


class SupportMessage(db.Model):
    """Anonymous support message. Deliberately has no user_id -- not even an
    admin can trace it back to a student, which is the point of it."""

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class BloodDonor(db.Model):
    """A student's donor profile -- one per account."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True, index=True)
    blood_group = db.Column(db.String(5), nullable=False)
    available = db.Column(db.Boolean, nullable=False, default=True)
    location = db.Column(db.String(150), nullable=True)
    # Only ever shown to a requester after this donor accepts a specific
    # ping -- never listed publicly. Contact happens through the app, not by
    # broadcasting a phone number to every student who opens the page.
    phone = db.Column(db.String(32), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])


class BloodRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    blood_group = db.Column(db.String(5), nullable=False, index=True)
    note = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="open")  # open|fulfilled
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    requested_by = db.relationship("User", foreign_keys=[requested_by_id])


class BloodPing(db.Model):
    """The requester asking one specific matching donor to respond --
    contact details are only ever shared once a donor accepts, not broadcast."""

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("blood_request.id"), nullable=False, index=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("blood_donor.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending|accepted|declined
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    request = db.relationship("BloodRequest", foreign_keys=[request_id])
    donor = db.relationship("BloodDonor", foreign_keys=[donor_id])

    __table_args__ = (db.UniqueConstraint("request_id", "donor_id", name="uq_ping_request_donor"),)
