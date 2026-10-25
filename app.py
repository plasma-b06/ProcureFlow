import re
import sqlite3
from urllib.parse import urlparse

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from models import User

app = Flask(__name__)
app.config.from_object(Config)

csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


# ---------- database ----------
def get_database():
    """Open a connection to instance/procureflow.db. Callers close it in `finally`."""
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # must be set on every connection
    return conn


def init_database():
    """Create any missing tables from schema.sql. Existing data is never touched."""
    conn = get_database()
    try:
        with open(app.config["SCHEMA"], encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()


init_database()

# One query used wherever we need a user together with the team (vendor company) they belong to.
USER_SQL = """
    SELECT u.id, u.name, u.email, u.password_hash, u.role, u.vendor_id, u.is_active,
           v.company_name AS vendor_name, v.status AS vendor_status
    FROM users u
    LEFT JOIN vendors v ON v.id = u.vendor_id
"""


@login_manager.user_loader
def load_user(user_id):
    db = get_database()
    try:
        row = db.execute(USER_SQL + " WHERE u.id = ?", (user_id,)).fetchone()
    finally:
        db.close()
    if row is None:
        return None
    user = User(row)
    # A deactivated user (or one whose vendor company was deactivated) is logged out on the next request.
    return None if user.team_problem() else user


# ---------- helpers ----------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TEAM_SIZES = ["Just me", "2–10", "11–50", "51–200", "200+"]


def safe_next(target):
    """Only allow same-site relative redirects after login."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        if not urlparse(target).netloc:
            return target
    return None


# ---------- public pages ----------
@app.route("/")
def home():
    """Public landing / about page."""
    return render_template("landing.html")


@app.route("/request-demo", methods=["GET", "POST"])
def request_demo():
    """Replaces public signup: accounts are created for teams, not by visitors."""
    errors = {}
    form = {"name": "", "email": "", "company": "", "team_size": "", "message": ""}

    if request.method == "POST":
        for key in form:
            form[key] = request.form.get(key, "").strip()
        form["email"] = form["email"].lower()

        if len(form["name"]) < 2:
            errors["name"] = "Enter your full name."
        if not EMAIL_RE.match(form["email"]):
            errors["email"] = "Enter a valid work email."
        if len(form["company"]) < 2:
            errors["company"] = "Enter your company name."
        if form["team_size"] not in TEAM_SIZES:
            errors["team_size"] = "Choose a team size."
        if len(form["message"]) > 1000:
            errors["message"] = "Keep this under 1000 characters."

        if not errors:
            db = get_database()
            try:
                db.execute(
                    """INSERT INTO demo_requests (name, email, company, team_size, message)
                       VALUES (?, ?, ?, ?, ?)""",
                    (form["name"], form["email"], form["company"], form["team_size"], form["message"] or None),
                )
                db.commit()
            except sqlite3.Error:
                db.rollback()
                flash("Could not save your request. Please try again.", "error")
            else:
                flash("Thanks. We have your request and will reply within one business day.", "success")
                return redirect(url_for("home"))
            finally:
                db.close()

    return render_template("request_demo.html", errors=errors, form=form, team_sizes=TEAM_SIZES), (400 if errors else 200)


@app.route("/signup")
def signup():
    """Old link: self-signup no longer exists."""
    return redirect(url_for("request_demo"))


# ---------- authentication ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    errors, email = {}, ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_database()
        try:
            row = db.execute(USER_SQL + " WHERE u.email = ?", (email,)).fetchone()
        finally:
            db.close()

        if not email or not password:
            errors["form"] = "Enter your email and password."
        elif row is None or not check_password_hash(row["password_hash"], password):
            # Same message for unknown email and wrong password.
            errors["form"] = "Email or password is incorrect."
            errors["demo_link"] = True
        else:
            # Password is correct: now check that the user belongs to an active team.
            user = User(row)
            problem = user.team_problem()
            if problem:
                errors["form"] = problem
            else:
                login_user(user, remember=bool(request.form.get("remember")))
                return redirect(safe_next(request.args.get("next")) or url_for("dashboard"))

    return render_template("login.html", errors=errors, email=email), (400 if errors else 200)


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


# ---------- demo data ----------
DEMO_PASSWORD = "Demo@1234"


@app.cli.command("seed-demo")
def seed_demo():
    """Create demo vendors and team accounts (development only). Safe to re-run."""
    vendors = [
        ("Acme Steel Co.", "Rajesh Iyer", "sales@acmesteel.demo", "+91 98200 11111", "27AABCA1234F1Z5",
         "Plot 14, MIDC Chinchwad, Pune, Maharashtra 411019"),
        ("Stellar Components Pvt Ltd", "Meera Nair", "quotes@stellar.demo", "+91 98200 22222", "27AAECS5678K1Z2",
         "Unit 7, Bhosari Industrial Estate, Pune, Maharashtra 411026"),
    ]
    accounts = [
        ("Asha Admin", "admin@procureflow.demo", "admin", None),
        ("Hemant Pande", "officer@procureflow.demo", "procurement_officer", None),
        ("Rajesh Iyer", "vendor1@procureflow.demo", "vendor", "27AABCA1234F1Z5"),
        ("Meera Nair", "vendor2@procureflow.demo", "vendor", "27AAECS5678K1Z2"),
        ("Marcus Manager", "manager@procureflow.demo", "manager", None),
    ]

    db = get_database()
    try:
        for company, contact, email, phone, gst, address in vendors:
            if not db.execute("SELECT id FROM vendors WHERE gst_number = ?", (gst,)).fetchone():
                db.execute(
                    """INSERT INTO vendors (company_name, contact_person, email, phone, gst_number, address)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (company, contact, email, phone, gst, address),
                )

        for name, email, role, gst in accounts:
            if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                continue
            vendor_id = None
            if gst:
                vendor_id = db.execute("SELECT id FROM vendors WHERE gst_number = ?", (gst,)).fetchone()["id"]
            db.execute(
                "INSERT INTO users (name, email, password_hash, role, vendor_id) VALUES (?, ?, ?, ?, ?)",
                (name, email, generate_password_hash(DEMO_PASSWORD), role, vendor_id),
            )
        db.commit()
    except sqlite3.Error as e:
        db.rollback()
        raise SystemExit(f"Seeding failed: {e}")
    finally:
        db.close()

    print("Demo accounts (development only):")
    for _, email, role, _ in accounts:
        print(f"  {role:<20} {email:<28} password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)