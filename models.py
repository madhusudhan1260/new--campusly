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


class Bookmark(db.Model):
    """A student saving a hackathon/internship for later."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "opportunity_id", name="uq_bookmark_user_opportunity"),)
