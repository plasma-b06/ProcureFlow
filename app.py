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
    """Role-aware home page with live counts and recent activity."""
    db = get_database()
    try:
        role = current_user.role
        metrics = []
        open_rfqs = []
        recent_quotes = []
        pending_approvals = []
        invited_rfqs = []
        my_quotes = []

        # ------------------------------------------------------------------
        # Procurement officer / admin / manager
        # ------------------------------------------------------------------
        if role in ("procurement_officer", "admin", "manager"):
            # Metric cards
            row = db.execute(
                "SELECT COUNT(*) AS n FROM rfqs WHERE status = 'published'"
            ).fetchone()
            metrics.append({
                "label": "Open RFQs",
                "value": row["n"],
                "hint": "Published & accepting quotes",
                "href": url_for("rfqs_list", status="published"),
            })

            row = db.execute(
                "SELECT COUNT(*) AS n FROM quotations WHERE status = 'submitted'"
            ).fetchone()
            metrics.append({
                "label": "Awaiting review",
                "value": row["n"],
                "hint": "Submitted quotations",
                "href": url_for("quotations_list"),
            })

            row = db.execute(
                "SELECT COUNT(*) AS n FROM quotations WHERE status = 'pending_approval'"
            ).fetchone()
            metrics.append({
                "label": "Pending approval",
                "value": row["n"],
                "hint": "Waiting on manager",
                "href": url_for("quotations_list"),
            })

            row = db.execute(
                "SELECT COUNT(*) AS n FROM vendors WHERE status = 'active'"
            ).fetchone()
            metrics.append({
                "label": "Active vendors",
                "value": row["n"],
                "hint": "Can be invited to RFQs",
                "href": url_for("vendors_list", status="active"),
            })

            # Open RFQs table (published + draft for officers)
            open_rfqs = db.execute(
                """
                SELECT r.id, r.rfq_number, r.title, r.deadline, r.status,
                       (SELECT COUNT(*) FROM rfq_vendors WHERE rfq_id = r.id) AS invited_count,
                       (SELECT COUNT(*) FROM quotations
                        WHERE rfq_id = r.id AND status != 'draft') AS quotation_count
                FROM rfqs r
                WHERE r.status IN ('draft', 'published')
                ORDER BY
                    CASE r.status WHEN 'published' THEN 0 ELSE 1 END,
                    r.deadline ASC
                LIMIT 8
                """
            ).fetchall()

            # Recent non-draft quotations
            recent_quotes = db.execute(
                """
                SELECT q.id, q.quotation_number, q.total_amount_paise, q.status,
                       r.rfq_number, r.title AS rfq_title,
                       v.company_name AS vendor_name
                FROM quotations q
                JOIN rfqs r ON r.id = q.rfq_id
                JOIN vendors v ON v.id = q.vendor_id
                WHERE q.status != 'draft'
                ORDER BY q.submitted_at DESC, q.id DESC
                LIMIT 8
                """
            ).fetchall()

            # Pending approvals (managers + admin)
            if role in ("manager", "admin"):
                pending_approvals = db.execute(
                    """
                    SELECT a.id, a.quotation_id, a.requested_at,
                           q.quotation_number, q.total_amount_paise,
                           r.rfq_number, v.company_name AS vendor_name
                    FROM approvals a
                    JOIN quotations q ON q.id = a.quotation_id
                    JOIN rfqs r ON r.id = q.rfq_id
                    JOIN vendors v ON v.id = q.vendor_id
                    WHERE a.decision = 'pending'
                    ORDER BY a.requested_at ASC
                    LIMIT 10
                    """
                ).fetchall()

        # ------------------------------------------------------------------
        # Vendor
        # ------------------------------------------------------------------
        elif role == "vendor":
            vid = current_user.vendor_id

            row = db.execute(
                """
                SELECT COUNT(*) AS n FROM rfq_vendors rv
                JOIN rfqs r ON r.id = rv.rfq_id
                WHERE rv.vendor_id = ? AND r.status = 'published'
                """,
                (vid,),
            ).fetchone()
            metrics.append({
                "label": "Open invitations",
                "value": row["n"],
                "hint": "Published RFQs you can quote on",
                "href": url_for("rfqs_list", status="published"),
            })

            row = db.execute(
                "SELECT COUNT(*) AS n FROM quotations WHERE vendor_id = ? AND status = 'draft'",
                (vid,),
            ).fetchone()
            metrics.append({
                "label": "Draft quotations",
                "value": row["n"],
                "hint": "Still editable",
                "href": url_for("quotations_list"),
            })

            row = db.execute(
                """
                SELECT COUNT(*) AS n FROM quotations
                WHERE vendor_id = ? AND status IN ('submitted', 'shortlisted', 'pending_approval')
                """,
                (vid,),
            ).fetchone()
            metrics.append({
                "label": "Under review",
                "value": row["n"],
                "hint": "Submitted or shortlisted",
                "href": url_for("quotations_list"),
            })

            row = db.execute(
                "SELECT COUNT(*) AS n FROM quotations WHERE vendor_id = ? AND status = 'approved'",
                (vid,),
            ).fetchone()
            metrics.append({
                "label": "Approved",
                "value": row["n"],
                "hint": "Won bids",
                "href": url_for("quotations_list"),
            })

            # Invited RFQs with my quotation status
            invited_rfqs = db.execute(
                """
                SELECT r.id, r.rfq_number, r.title, r.deadline, r.status,
                       q.status AS my_status
                FROM rfq_vendors rv
                JOIN rfqs r ON r.id = rv.rfq_id
                LEFT JOIN quotations q ON q.rfq_id = r.id AND q.vendor_id = rv.vendor_id
                WHERE rv.vendor_id = ? AND r.status != 'draft'
                ORDER BY r.deadline ASC
                LIMIT 8
                """,
                (vid,),
            ).fetchall()

            my_quotes = db.execute(
                """
                SELECT q.id, q.quotation_number, q.total_amount_paise, q.status,
                       r.rfq_number, r.title AS rfq_title
                FROM quotations q
                JOIN rfqs r ON r.id = q.rfq_id
                WHERE q.vendor_id = ?
                ORDER BY q.created_at DESC
                LIMIT 8
                """,
                (vid,),
            ).fetchall()

    finally:
        db.close()

    return render_template(
        "dashboard.html",
        metrics=metrics,
        open_rfqs=open_rfqs,
        recent_quotes=recent_quotes,
        pending_approvals=pending_approvals,
        invited_rfqs=invited_rfqs,
        my_quotes=my_quotes,
    )


# ===========================================================================
# Helpers used by vendors / RFQs / quotations
# ===========================================================================

from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def _role(*roles):
    """Return True if current_user has one of the given roles (admin always passes)."""
    if not current_user.is_authenticated:
        return False
    return current_user.role in roles or current_user.role == "admin"


def _next_number(db, prefix: str, table: str, column: str) -> str:
    year = date.today().year
    row = db.execute(
        f"SELECT {column} FROM {table} WHERE {column} LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}-{year}-%",),
    ).fetchone()
    seq = 1
    if row:
        try:
            seq = int(row[0].rsplit("-", 1)[-1]) + 1
        except ValueError:
            pass
    return f"{prefix}-{year}-{seq:04d}"


def _paise(value) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def _log(db, action: str, entity_type: str, entity_id: int, details: str = None):
    db.execute(
        "INSERT INTO activity_logs (user_id, action, entity_type, entity_id, details) VALUES (?,?,?,?,?)",
        (current_user.id, action, entity_type, entity_id, details),
    )


# ===========================================================================
# Vendors
# ===========================================================================

@app.route("/vendors")
@login_required
def vendors_list():
    if not _role("procurement_officer", "manager", "admin"):
        flash("You do not have access to the vendor list.", "error")
        return redirect(url_for("dashboard"))

    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()

    sql = "SELECT * FROM vendors WHERE 1=1"
    params = []
    if q:
        sql += " AND company_name LIKE ?"
        params.append(f"%{q}%")
    if status in ("active", "inactive"):
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY company_name COLLATE NOCASE"

    db = get_database()
    try:
        vendors = db.execute(sql, params).fetchall()
    finally:
        db.close()

    return render_template("vendors.html", vendors=vendors, q=q, status=status)


@app.route("/vendors/add", methods=["POST"])
@login_required
def vendors_add():
    if not _role("procurement_officer", "admin"):
        flash("Only procurement officers can add vendors.", "error")
        return redirect(url_for("vendors_list"))

    company = (request.form.get("company_name") or "").strip()
    contact = (request.form.get("contact_person") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip() or None
    gst = (request.form.get("gst_number") or "").strip() or None
    address = (request.form.get("address") or "").strip() or None

    if not company or not contact or not email:
        flash("Company name, contact person and email are required.", "error")
        return redirect(url_for("vendors_list"))

    db = get_database()
    try:
        db.execute(
            """INSERT INTO vendors
               (company_name, contact_person, email, phone, gst_number, address, status)
               VALUES (?,?,?,?,?,?, 'active')""",
            (company, contact, email, phone, gst, address),
        )
        db.commit()
        flash(f"Vendor “{company}” added.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("A vendor with that GST number already exists.", "error")
    finally:
        db.close()
    return redirect(url_for("vendors_list"))


@app.route("/vendors/<int:vid>/edit", methods=["POST"])
@login_required
def vendors_edit(vid):
    if not _role("procurement_officer", "admin"):
        flash("Only procurement officers can edit vendors.", "error")
        return redirect(url_for("vendors_list"))

    company = (request.form.get("company_name") or "").strip()
    contact = (request.form.get("contact_person") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip() or None
    gst = (request.form.get("gst_number") or "").strip() or None
    address = (request.form.get("address") or "").strip() or None

    if not company or not contact or not email:
        flash("Company name, contact person and email are required.", "error")
        return redirect(url_for("vendors_list"))

    db = get_database()
    try:
        db.execute(
            """UPDATE vendors SET
               company_name=?, contact_person=?, email=?, phone=?, gst_number=?, address=?,
               updated_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE id=?""",
            (company, contact, email, phone, gst, address, vid),
        )
        db.commit()
        flash("Vendor updated.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("A vendor with that GST number already exists.", "error")
    finally:
        db.close()
    return redirect(url_for("vendors_list"))


@app.route("/vendors/<int:vid>/deactivate", methods=["POST"])
@login_required
def vendors_deactivate(vid):
    if not _role("procurement_officer", "admin"):
        flash("Only procurement officers can deactivate vendors.", "error")
        return redirect(url_for("vendors_list"))

    db = get_database()
    try:
        db.execute(
            """UPDATE vendors SET status='inactive',
               updated_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id=?""",
            (vid,),
        )
        db.commit()
        flash("Vendor deactivated.", "success")
    finally:
        db.close()
    return redirect(url_for("vendors_list"))


# ===========================================================================
# RFQs
# ===========================================================================

@app.route("/rfqs")
@login_required
def rfqs_list():
    status = (request.args.get("status") or "").strip()
    is_vendor = current_user.role == "vendor"

    db = get_database()
    try:
        if is_vendor:
            sql = """
                SELECT r.id, r.rfq_number, r.title, r.deadline, r.status,
                       (SELECT COUNT(*) FROM rfq_items WHERE rfq_id = r.id) AS item_count,
                       0 AS invited_count,
                       (SELECT COUNT(*) FROM quotations q
                        WHERE q.rfq_id = r.id AND q.vendor_id = ?
                          AND q.status NOT IN ('draft')) AS quotation_count
                FROM rfqs r
                JOIN rfq_vendors rv ON rv.rfq_id = r.id AND rv.vendor_id = ?
                WHERE r.status != 'draft'
            """
            params = [current_user.vendor_id, current_user.vendor_id]
            if status:
                sql += " AND r.status = ?"
                params.append(status)
            sql += " ORDER BY r.deadline DESC, r.id DESC"
            rfqs = db.execute(sql, params).fetchall()
            active_vendors = []
        else:
            sql = """
                SELECT r.id, r.rfq_number, r.title, r.deadline, r.status,
                       (SELECT COUNT(*) FROM rfq_items WHERE rfq_id = r.id) AS item_count,
                       (SELECT COUNT(*) FROM rfq_vendors WHERE rfq_id = r.id) AS invited_count,
                       (SELECT COUNT(*) FROM quotations
                        WHERE rfq_id = r.id AND status NOT IN ('draft')) AS quotation_count
                FROM rfqs r
                WHERE 1=1
            """
            params = []
            if status:
                sql += " AND r.status = ?"
                params.append(status)
            sql += " ORDER BY r.created_at DESC"
            rfqs = db.execute(sql, params).fetchall()
            active_vendors = db.execute(
                "SELECT id, company_name FROM vendors WHERE status = 'active' ORDER BY company_name"
            ).fetchall()
    finally:
        db.close()

    return render_template(
        "rfqs.html",
        rfqs=rfqs,
        status=status,
        active_vendors=active_vendors,
        today=date.today().isoformat(),
    )


@app.route("/rfqs/<int:rid>")
@login_required
def rfq_detail(rid):
    db = get_database()
    try:
        rfq = db.execute(
            """SELECT r.*, u.name AS created_by_name
               FROM rfqs r
               JOIN users u ON u.id = r.created_by
               WHERE r.id = ?""",
            (rid,),
        ).fetchone()
        if not rfq:
            flash("RFQ not found.", "error")
            return redirect(url_for("rfqs_list"))

        is_vendor = current_user.role == "vendor"

        if is_vendor:
            invite = db.execute(
                "SELECT 1 FROM rfq_vendors WHERE rfq_id = ? AND vendor_id = ?",
                (rid, current_user.vendor_id),
            ).fetchone()
            if not invite or rfq["status"] == "draft":
                flash("You do not have access to this RFQ.", "error")
                return redirect(url_for("rfqs_list"))

        items = db.execute(
            "SELECT * FROM rfq_items WHERE rfq_id = ? ORDER BY id", (rid,)
        ).fetchall()

        invited_vendors = []
        my_quotation = None

        if not is_vendor:
            invited_vendors = db.execute(
                """
                SELECT v.id AS vendor_id, v.company_name,
                       rv.status AS invite_status,
                       q.id AS quotation_id, q.status AS quotation_status,
                       q.total_amount_paise
                FROM rfq_vendors rv
                JOIN vendors v ON v.id = rv.vendor_id
                LEFT JOIN quotations q ON q.rfq_id = rv.rfq_id AND q.vendor_id = rv.vendor_id
                WHERE rv.rfq_id = ?
                ORDER BY v.company_name
                """,
                (rid,),
            ).fetchall()
        else:
            q = db.execute(
                "SELECT id, status FROM quotations WHERE rfq_id = ? AND vendor_id = ?",
                (rid, current_user.vendor_id),
            ).fetchone()
            if q:
                my_quotation = dict(q)

        deadline_passed = date.fromisoformat(rfq["deadline"][:10]) < date.today()
    finally:
        db.close()

    return render_template(
        "rfqs.html",
        rfq=rfq,
        items=items,
        invited_vendors=invited_vendors,
        deadline_passed=deadline_passed,
        my_quotation=my_quotation,
    )


@app.route("/rfqs/create", methods=["POST"])
@login_required
def rfqs_create():
    if not _role("procurement_officer", "admin"):
        flash("Only procurement officers can create RFQs.", "error")
        return redirect(url_for("rfqs_list"))

    title = (request.form.get("title") or "").strip()
    deadline = (request.form.get("deadline") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    action = request.form.get("action", "draft")  # draft | publish

    names = request.form.getlist("item_name[]")
    qtys = request.form.getlist("item_quantity[]")
    units = request.form.getlist("item_unit[]")
    descs = request.form.getlist("item_description[]")
    vendor_ids = [int(v) for v in request.form.getlist("vendor_ids[]") if str(v).isdigit()]

    if not title or not deadline:
        flash("Title and deadline are required.", "error")
        return redirect(url_for("rfqs_list"))
    if not any((n or "").strip() for n in names):
        flash("At least one item is required.", "error")
        return redirect(url_for("rfqs_list"))

    status = "published" if action == "publish" else "draft"

    db = get_database()
    try:
        rfq_number = _next_number(db, "RFQ", "rfqs", "rfq_number")
        cur = db.execute(
            """INSERT INTO rfqs (rfq_number, title, description, deadline, status, created_by)
               VALUES (?,?,?,?,?,?)""",
            (rfq_number, title, description, deadline, status, current_user.id),
        )
        rid = cur.lastrowid

        for name, qty, unit, desc in zip(names, qtys, units, descs):
            name = (name or "").strip()
            if not name:
                continue
            db.execute(
                """INSERT INTO rfq_items (rfq_id, item_name, description, quantity, unit)
                   VALUES (?,?,?,?,?)""",
                (rid, name, (desc or "").strip() or None, float(qty or 0), (unit or "").strip()),
            )

        for vid in vendor_ids:
            db.execute(
                "INSERT OR IGNORE INTO rfq_vendors (rfq_id, vendor_id, status) VALUES (?,?, 'invited')",
                (rid, vid),
            )
            # Pre-create a draft quotation so the vendor can open it immediately
            if status == "published":
                qnum = _next_number(db, "QTN", "quotations", "quotation_number")
                # Schema requires NOT NULL totals/days – use 0 for drafts
                qcur = db.execute(
                    """INSERT OR IGNORE INTO quotations
                       (quotation_number, rfq_id, vendor_id,
                        total_amount_paise, delivery_days, status)
                       VALUES (?,?,?, 0, 0, 'draft')""",
                    (qnum, rid, vid),
                )
                qid = qcur.lastrowid
                if qid:
                    items = db.execute(
                        "SELECT id FROM rfq_items WHERE rfq_id = ?", (rid,)
                    ).fetchall()
                    for it in items:
                        db.execute(
                            """INSERT INTO quotation_items
                               (quotation_id, rfq_item_id, unit_price_paise, line_total_paise)
                               VALUES (?,?, 0, 0)""",
                            (qid, it["id"]),
                        )

        _log(db, "RFQ_CREATED", "rfq", rid, f"Created {rfq_number}")
        if status == "published":
            _log(db, "RFQ_PUBLISHED", "rfq", rid, f"Published {rfq_number}")
        db.commit()
        flash(
            f"RFQ {rfq_number} {'published' if status == 'published' else 'saved as draft'}.",
            "success",
        )
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Could not create RFQ: {e}", "error")
        return redirect(url_for("rfqs_list"))
    finally:
        db.close()

    return redirect(url_for("rfq_detail", rid=rid))


@app.route("/rfqs/<int:rid>/publish", methods=["POST"])
@login_required
def rfqs_publish(rid):
    if not _role("procurement_officer", "admin"):
        flash("Only procurement officers can publish RFQs.", "error")
        return redirect(url_for("rfq_detail", rid=rid))

    db = get_database()
    try:
        rfq = db.execute("SELECT * FROM rfqs WHERE id = ?", (rid,)).fetchone()
        if not rfq:
            flash("RFQ not found.", "error")
            return redirect(url_for("rfqs_list"))
        if rfq["status"] != "draft":
            flash("Only draft RFQs can be published.", "error")
            return redirect(url_for("rfq_detail", rid=rid))

        db.execute(
            """UPDATE rfqs SET status = 'published',
               updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?""",
            (rid,),
        )

        invites = db.execute(
            "SELECT vendor_id FROM rfq_vendors WHERE rfq_id = ?", (rid,)
        ).fetchall()
        items = db.execute(
            "SELECT id FROM rfq_items WHERE rfq_id = ?", (rid,)
        ).fetchall()

        for inv in invites:
            exists = db.execute(
                "SELECT id FROM quotations WHERE rfq_id = ? AND vendor_id = ?",
                (rid, inv["vendor_id"]),
            ).fetchone()
            if not exists:
                qnum = _next_number(db, "QTN", "quotations", "quotation_number")
                qcur = db.execute(
                    """INSERT INTO quotations
                       (quotation_number, rfq_id, vendor_id,
                        total_amount_paise, delivery_days, status)
                       VALUES (?,?,?, 0, 0, 'draft')""",
                    (qnum, rid, inv["vendor_id"]),
                )
                qid = qcur.lastrowid
                for it in items:
                    db.execute(
                        """INSERT INTO quotation_items
                           (quotation_id, rfq_item_id, unit_price_paise, line_total_paise)
                           VALUES (?,?, 0, 0)""",
                        (qid, it["id"]),
                    )

        _log(db, "RFQ_PUBLISHED", "rfq", rid, f"Published {rfq['rfq_number']}")
        db.commit()
        flash("RFQ published. Invited vendors can now submit quotations.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Could not publish RFQ: {e}", "error")
    finally:
        db.close()

    return redirect(url_for("rfq_detail", rid=rid))


# ===========================================================================
# Quotations
# ===========================================================================

@app.route("/quotations")
@login_required
def quotations_list():
    rfq_id = request.args.get("rfq_id", type=int)
    is_vendor = current_user.role == "vendor"

    # Compare mode (officer / manager / admin)
    if rfq_id and not is_vendor:
        return _compare_quotations(rfq_id)

    db = get_database()
    try:
        if is_vendor:
            rows = db.execute(
                """
                SELECT q.id, q.quotation_number, q.rfq_id, r.rfq_number, r.title AS rfq_title,
                       NULL AS vendor_name, q.total_amount_paise, q.delivery_days,
                       q.status, q.submitted_at
                FROM quotations q
                JOIN rfqs r ON r.id = q.rfq_id
                WHERE q.vendor_id = ?
                ORDER BY q.created_at DESC
                """,
                (current_user.vendor_id,),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT q.id, q.quotation_number, q.rfq_id, r.rfq_number, r.title AS rfq_title,
                       v.company_name AS vendor_name, q.total_amount_paise, q.delivery_days,
                       q.status, q.submitted_at
                FROM quotations q
                JOIN rfqs r ON r.id = q.rfq_id
                JOIN vendors v ON v.id = q.vendor_id
                WHERE q.status != 'draft'
                ORDER BY q.submitted_at DESC, q.id DESC
                """
            ).fetchall()
    finally:
        db.close()

    return render_template("quotations.html", quotations=rows)


def _compare_quotations(rfq_id: int):
    db = get_database()
    try:
        rfq = db.execute(
            "SELECT id, rfq_number, title, deadline FROM rfqs WHERE id = ?", (rfq_id,)
        ).fetchone()
        if not rfq:
            flash("RFQ not found.", "error")
            return redirect(url_for("rfqs_list"))

        items = db.execute(
            "SELECT id, item_name, quantity, unit FROM rfq_items WHERE rfq_id = ? ORDER BY id",
            (rfq_id,),
        ).fetchall()

        quotes_raw = db.execute(
            """
            SELECT q.id, q.quotation_number, v.company_name AS vendor_name,
                   q.total_amount_paise, q.delivery_days, q.remarks, q.status
            FROM quotations q
            JOIN vendors v ON v.id = q.vendor_id
            WHERE q.rfq_id = ? AND q.status != 'draft'
            ORDER BY q.total_amount_paise ASC
            """,
            (rfq_id,),
        ).fetchall()

        quotes = []
        lowest_id = None
        lowest_total = None
        lowest_by_item = {}

        for q in quotes_raw:
            prices = {}
            lines = db.execute(
                """SELECT rfq_item_id, unit_price_paise, line_total_paise
                   FROM quotation_items WHERE quotation_id = ?""",
                (q["id"],),
            ).fetchall()
            for ln in lines:
                if ln["unit_price_paise"] is not None and ln["unit_price_paise"] > 0:
                    prices[ln["rfq_item_id"]] = {
                        "unit": ln["unit_price_paise"],
                        "line": ln["line_total_paise"],
                    }
                    prev = lowest_by_item.get(ln["rfq_item_id"])
                    if prev is None or ln["unit_price_paise"] < prev:
                        lowest_by_item[ln["rfq_item_id"]] = ln["unit_price_paise"]

            quotes.append(
                {
                    "id": q["id"],
                    "quotation_number": q["quotation_number"],
                    "vendor_name": q["vendor_name"],
                    "total_amount_paise": q["total_amount_paise"],
                    "delivery_days": q["delivery_days"],
                    "remarks": q["remarks"],
                    "status": q["status"],
                    "prices": prices,
                }
            )
            if q["total_amount_paise"] is not None and q["total_amount_paise"] > 0:
                if lowest_total is None or q["total_amount_paise"] < lowest_total:
                    lowest_total = q["total_amount_paise"]
                    lowest_id = q["id"]

        compare = {
            "rfq": rfq,
            "rfq_items": items,
            "quotes": quotes,
            "lowest_id": lowest_id,
            "lowest_by_item": lowest_by_item,
        }
    finally:
        db.close()

    return render_template("quotations.html", compare=compare)


@app.route("/quotations/<int:qid>")
@login_required
def quotation_detail(qid):
    db = get_database()
    try:
        q = db.execute(
            """
            SELECT q.*, r.rfq_number, r.title AS rfq_title, r.deadline AS rfq_deadline,
                   v.company_name AS vendor_name
            FROM quotations q
            JOIN rfqs r ON r.id = q.rfq_id
            JOIN vendors v ON v.id = q.vendor_id
            WHERE q.id = ?
            """,
            (qid,),
        ).fetchone()
        if not q:
            flash("Quotation not found.", "error")
            return redirect(url_for("quotations_list"))

        is_vendor = current_user.role == "vendor"
        if is_vendor and q["vendor_id"] != current_user.vendor_id:
            flash("You do not have access to this quotation.", "error")
            return redirect(url_for("quotations_list"))

        lines = db.execute(
            """
            SELECT qi.rfq_item_id, ri.item_name, ri.description, ri.quantity, ri.unit,
                   qi.unit_price_paise, qi.line_total_paise
            FROM quotation_items qi
            JOIN rfq_items ri ON ri.id = qi.rfq_item_id
            WHERE qi.quotation_id = ?
            ORDER BY ri.id
            """,
            (qid,),
        ).fetchall()

        deadline_passed = date.fromisoformat(q["rfq_deadline"][:10]) < date.today()
        editable = (
            is_vendor
            and q["status"] == "draft"
            and not deadline_passed
            and q["vendor_id"] == current_user.vendor_id
        )
        can_shortlist = (
            _role("procurement_officer", "admin")
            and q["status"] == "submitted"
        )
    finally:
        db.close()

    return render_template(
        "quotations.html",
        quotation=q,
        lines=lines,
        editable=editable,
        can_shortlist=can_shortlist,
    )


@app.route("/quotations/<int:qid>/submit", methods=["POST"])
@login_required
def quotation_submit(qid):
    if current_user.role != "vendor":
        flash("Only vendors can submit quotations.", "error")
        return redirect(url_for("quotations_list"))

    db = get_database()
    try:
        q = db.execute("SELECT * FROM quotations WHERE id = ?", (qid,)).fetchone()
        if not q:
            flash("Quotation not found.", "error")
            return redirect(url_for("quotations_list"))
        if q["vendor_id"] != current_user.vendor_id:
            flash("You do not own this quotation.", "error")
            return redirect(url_for("quotations_list"))
        if q["status"] != "draft":
            flash("Only draft quotations can be edited.", "error")
            return redirect(url_for("quotation_detail", qid=qid))

        rfq = db.execute(
            "SELECT deadline FROM rfqs WHERE id = ?", (q["rfq_id"],)
        ).fetchone()
        if date.fromisoformat(rfq["deadline"][:10]) < date.today():
            flash("The RFQ deadline has passed.", "error")
            return redirect(url_for("quotation_detail", qid=qid))

        action = request.form.get("action", "draft")  # draft | submit
        delivery_raw = request.form.get("delivery_days")
        remarks = (request.form.get("remarks") or "").strip() or None

        try:
            delivery_days = int(delivery_raw) if delivery_raw not in (None, "") else 0
        except ValueError:
            delivery_days = 0

        total = 0
        lines = db.execute(
            "SELECT rfq_item_id FROM quotation_items WHERE quotation_id = ?", (qid,)
        ).fetchall()

        for ln in lines:
            key = f"unit_price_{ln['rfq_item_id']}"
            unit_paise = _paise(request.form.get(key)) or 0
            qty_row = db.execute(
                "SELECT quantity FROM rfq_items WHERE id = ?", (ln["rfq_item_id"],)
            ).fetchone()
            qty = float(qty_row["quantity"]) if qty_row else 0
            line_total = int(round(unit_paise * qty))
            total += line_total
            db.execute(
                """UPDATE quotation_items
                   SET unit_price_paise = ?, line_total_paise = ?
                   WHERE quotation_id = ? AND rfq_item_id = ?""",
                (unit_paise, line_total, qid, ln["rfq_item_id"]),
            )

        status = "submitted" if action == "submit" else "draft"
        submitted_at = (
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if action == "submit"
            else None
        )

        db.execute(
            """UPDATE quotations SET
               total_amount_paise = ?, delivery_days = ?, remarks = ?,
               status = ?, submitted_at = ?,
               updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE id = ?""",
            (total, delivery_days, remarks, status, submitted_at, qid),
        )

        if action == "submit":
            db.execute(
                """UPDATE rfq_vendors SET status = 'responded'
                   WHERE rfq_id = ? AND vendor_id = ?""",
                (q["rfq_id"], q["vendor_id"]),
            )
            _log(db, "QUOTATION_SUBMITTED", "quotation", qid, f"Submitted {q['quotation_number']}")

        db.commit()
        flash(
            "Quotation submitted." if action == "submit" else "Draft saved.",
            "success",
        )
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Could not save quotation: {e}", "error")
    finally:
        db.close()

    return redirect(url_for("quotation_detail", qid=qid))


@app.route("/quotations/<int:qid>/shortlist", methods=["POST"])
@login_required
def quotation_shortlist(qid):
    if not _role("procurement_officer", "admin"):
        flash("Only procurement officers can shortlist quotations.", "error")
        return redirect(url_for("quotations_list"))

    db = get_database()
    try:
        q = db.execute(
            "SELECT id, rfq_id, quotation_number, status FROM quotations WHERE id = ?",
            (qid,),
        ).fetchone()
        if not q or q["status"] != "submitted":
            flash("Only submitted quotations can be shortlisted.", "error")
            return redirect(url_for("quotations_list"))

        db.execute(
            """UPDATE quotations SET status = 'pending_approval',
               updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE id = ?""",
            (qid,),
        )
        # Create a pending approval row for the manager workflow
        managers = db.execute(
            "SELECT id FROM users WHERE role = 'manager' AND is_active = 1"
        ).fetchall()
        for m in managers:
            db.execute(
                """INSERT INTO approvals (quotation_id, manager_id, decision)
                   VALUES (?, ?, 'pending')""",
                (qid, m["id"]),
            )

        _log(db, "QUOTATION_SHORTLISTED", "quotation", qid, f"Shortlisted {q['quotation_number']}")
        db.commit()
        flash("Quotation shortlisted and sent for manager approval.", "success")
        return redirect(url_for("quotations_list", rfq_id=q["rfq_id"]))
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Could not shortlist: {e}", "error")
        return redirect(url_for("quotation_detail", qid=qid))
    finally:
        db.close()


# ===========================================================================
# Shared helpers for approvals / orders / invoices
# ===========================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_plus(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _begin(db):
    """Take the write lock up front so two people cannot act on the same record at once."""
    db.execute("BEGIN IMMEDIATE")


# Overdue is derived, not stored: an unpaid invoice past its due date is shown as overdue.
INVOICE_STATUS_SQL = """
    CASE WHEN i.payment_status = 'unpaid' AND i.due_date < date('now')
         THEN 'overdue' ELSE i.payment_status END
"""

INVOICE_LINES_SQL = """
    SELECT ri.item_name, ri.description, ri.quantity, ri.unit,
           qi.unit_price_paise, qi.line_total_paise
    FROM purchase_orders po
    JOIN quotation_items qi ON qi.quotation_id = po.quotation_id
    JOIN rfq_items ri ON ri.id = qi.rfq_item_id
    WHERE po.id = ?
    ORDER BY ri.id
"""


# ===========================================================================
# Approvals (managers decide; admin can view)
# ===========================================================================

@app.route("/approvals")
@login_required
def approvals_list():
    if current_user.role not in ("manager", "admin"):
        flash("You do not have access to approvals.", "error")
        return redirect(url_for("dashboard"))

    db = get_database()
    try:
        # A manager sees the requests assigned to them. Admin sees each request once.
        if current_user.role == "manager":
            scope_sql, scope_params = "AND a.manager_id = ?", (current_user.id,)
        else:
            scope_sql = ("AND a.id = (SELECT MIN(id) FROM approvals "
                         "WHERE quotation_id = a.quotation_id AND decision = 'pending')")
            scope_params = ()

        pending_rows = db.execute(
            f"""
            SELECT a.id, a.quotation_id, a.requested_at,
                   q.quotation_number, q.total_amount_paise, q.delivery_days,
                   r.id AS rfq_id, r.rfq_number, r.title AS rfq_title,
                   v.company_name AS vendor_name
            FROM approvals a
            JOIN quotations q ON q.id = a.quotation_id
            JOIN rfqs r ON r.id = q.rfq_id
            JOIN vendors v ON v.id = q.vendor_id
            WHERE a.decision = 'pending' AND q.status = 'pending_approval' {scope_sql}
            ORDER BY a.requested_at ASC, a.id ASC
            """,
            scope_params,
        ).fetchall()

        pending = []
        for row in pending_rows:
            item = dict(row)
            item["lines"] = db.execute(
                """
                SELECT ri.item_name, ri.quantity, ri.unit, qi.unit_price_paise, qi.line_total_paise
                FROM quotation_items qi
                JOIN rfq_items ri ON ri.id = qi.rfq_item_id
                WHERE qi.quotation_id = ?
                ORDER BY ri.id
                """,
                (row["quotation_id"],),
            ).fetchall()
            pending.append(item)

        history = db.execute(
            """
            SELECT q.quotation_number, r.rfq_number, v.company_name AS vendor_name,
                   q.total_amount_paise, a.decision, a.remarks, a.decided_at,
                   u.name AS manager_name
            FROM approvals a
            JOIN quotations q ON q.id = a.quotation_id
            JOIN rfqs r ON r.id = q.rfq_id
            JOIN vendors v ON v.id = q.vendor_id
            JOIN users u ON u.id = a.manager_id
            WHERE a.decision != 'pending'
            ORDER BY a.decided_at DESC, a.id DESC
            LIMIT 50
            """
        ).fetchall()
    finally:
        db.close()

    return render_template("approvals.html", pending=pending, history=history)


def _decide_approval(aid: int, decision: str, remarks):
    """Record a manager's decision in ONE transaction.

    Approve: approval -> approved, quotation -> approved, exactly one purchase order, RFQ -> closed.
    Reject:  approval -> rejected (remarks required), quotation -> rejected.
    Returns (ok, message, po_id).
    """
    db = get_database()
    try:
        _begin(db)
        a = db.execute(
            """
            SELECT a.id, a.manager_id, a.decision, a.quotation_id,
                   q.status AS q_status, q.quotation_number, q.rfq_id, q.vendor_id,
                   q.total_amount_paise, r.rfq_number
            FROM approvals a
            JOIN quotations q ON q.id = a.quotation_id
            JOIN rfqs r ON r.id = q.rfq_id
            WHERE a.id = ?
            """,
            (aid,),
        ).fetchone()

        if a is None:
            db.rollback()
            return False, "Approval request not found.", None
        if a["manager_id"] != current_user.id:
            db.rollback()
            return False, "This approval request is assigned to another manager.", None
        if a["decision"] != "pending" or a["q_status"] != "pending_approval":
            db.rollback()
            return False, "This request has already been decided.", None

        now = _now_iso()
        cur = db.execute(
            "UPDATE approvals SET decision = ?, remarks = ?, decided_at = ? WHERE id = ? AND decision = 'pending'",
            (decision, remarks, now, aid),
        )
        if cur.rowcount != 1:
            db.rollback()
            return False, "This request has already been decided.", None

        # Other managers were sent the same request; it is settled now.
        db.execute(
            "DELETE FROM approvals WHERE quotation_id = ? AND decision = 'pending' AND id != ?",
            (a["quotation_id"], aid),
        )

        po_id = None
        if decision == "approved":
            if not a["total_amount_paise"] or a["total_amount_paise"] <= 0:
                db.rollback()
                return False, "This quotation has a zero total and cannot be approved.", None
            awarded = db.execute(
                "SELECT 1 FROM quotations WHERE rfq_id = ? AND status = 'approved'", (a["rfq_id"],)
            ).fetchone()
            if awarded:
                db.rollback()
                return False, f"{a['rfq_number']} already has an approved quotation.", None

            db.execute(
                "UPDATE quotations SET status = 'approved', updated_at = ? WHERE id = ? AND status = 'pending_approval'",
                (now, a["quotation_id"]),
            )
            po_number = _next_number(db, "PO", "purchase_orders", "po_number")
            po_id = db.execute(
                """INSERT INTO purchase_orders (po_number, quotation_id, vendor_id, total_amount_paise)
                   VALUES (?, ?, ?, ?)""",
                (po_number, a["quotation_id"], a["vendor_id"], a["total_amount_paise"]),
            ).lastrowid
            db.execute("UPDATE rfqs SET status = 'closed', updated_at = ? WHERE id = ?", (now, a["rfq_id"]))

            _log(db, "QUOTATION_APPROVED", "quotation", a["quotation_id"], f"Approved {a['quotation_number']}")
            _log(db, "PO_GENERATED", "purchase_order", po_id, f"{po_number} from {a['quotation_number']}")
            message = f"Approved. Purchase order {po_number} was created."
        else:
            db.execute(
                "UPDATE quotations SET status = 'rejected', updated_at = ? WHERE id = ?",
                (now, a["quotation_id"]),
            )
            _log(db, "QUOTATION_REJECTED", "quotation", a["quotation_id"],
                 f"Rejected {a['quotation_number']}: {remarks}")
            message = "Quotation rejected. The procurement officer can shortlist another bid."

        db.commit()
        return True, message, po_id
    except sqlite3.IntegrityError:
        db.rollback()
        return False, "A purchase order already exists for this quotation.", None
    except sqlite3.Error as e:
        db.rollback()
        return False, f"Could not save the decision: {e}", None
    finally:
        db.close()


@app.route("/approvals/<int:aid>/approve", methods=["POST"])
@login_required
def approval_approve(aid):
    # Managers only. Admin can view approvals but not decide them.
    if current_user.role != "manager":
        flash("Only managers can approve quotations.", "error")
        return redirect(url_for("approvals_list"))

    remarks = (request.form.get("remarks") or "").strip() or None
    ok, message, _po_id = _decide_approval(aid, "approved", remarks)
    flash(message, "success" if ok else "error")
    return redirect(url_for("approvals_list"))


@app.route("/approvals/<int:aid>/reject", methods=["POST"])
@login_required
def approval_reject(aid):
    if current_user.role != "manager":
        flash("Only managers can reject quotations.", "error")
        return redirect(url_for("approvals_list"))

    remarks = (request.form.get("remarks") or "").strip()
    if not remarks:
        flash("Remarks are required when rejecting a quotation.", "error")
        return redirect(url_for("approvals_list"))

    ok, message, _ = _decide_approval(aid, "rejected", remarks)
    flash(message, "success" if ok else "error")
    return redirect(url_for("approvals_list"))


# ===========================================================================
# Purchase orders
# ===========================================================================

@app.route("/orders")
@login_required
def orders_list():
    if current_user.role not in ("admin", "procurement_officer", "vendor"):
        flash("You do not have access to purchase orders.", "error")
        return redirect(url_for("dashboard"))

    sql = """
        SELECT po.id, po.po_number, r.rfq_number, v.company_name AS vendor_name,
               po.total_amount_paise, po.status, po.created_at
        FROM purchase_orders po
        JOIN quotations q ON q.id = po.quotation_id
        JOIN rfqs r ON r.id = q.rfq_id
        JOIN vendors v ON v.id = po.vendor_id
    """
    params = []
    if current_user.role == "vendor":
        sql += " WHERE po.vendor_id = ?"
        params.append(current_user.vendor_id)
    sql += " ORDER BY po.created_at DESC, po.id DESC"

    db = get_database()
    try:
        orders = db.execute(sql, params).fetchall()
    finally:
        db.close()

    return render_template("orders.html", orders=orders)


@app.route("/orders/<int:oid>")
@login_required
def order_detail(oid):
    if current_user.role not in ("admin", "procurement_officer", "vendor"):
        flash("You do not have access to purchase orders.", "error")
        return redirect(url_for("dashboard"))

    db = get_database()
    try:
        order = db.execute(
            """
            SELECT po.id, po.po_number, po.vendor_id, po.total_amount_paise, po.status, po.created_at,
                   q.quotation_number, q.delivery_days,
                   r.rfq_number, r.title AS rfq_title,
                   v.company_name AS vendor_name, v.contact_person, v.email AS vendor_email,
                   v.phone, v.gst_number, v.address
            FROM purchase_orders po
            JOIN quotations q ON q.id = po.quotation_id
            JOIN rfqs r ON r.id = q.rfq_id
            JOIN vendors v ON v.id = po.vendor_id
            WHERE po.id = ?
            """,
            (oid,),
        ).fetchone()

        # Vendors can only open their own orders. Same message as "not found" so ids cannot be probed.
        if order is None or (current_user.role == "vendor" and order["vendor_id"] != current_user.vendor_id):
            flash("Purchase order not found.", "error")
            return redirect(url_for("orders_list"))

        lines = db.execute(INVOICE_LINES_SQL, (oid,)).fetchall()
        inv = db.execute(
            "SELECT id, invoice_number FROM invoices WHERE purchase_order_id = ?", (oid,)
        ).fetchone()
    finally:
        db.close()

    return render_template(
        "orders.html",
        order=order,
        lines=lines,
        invoice=dict(inv) if inv else None,
        default_tax_rate=18,
        default_due_date=_today_plus(30),
    )


# ===========================================================================
# Invoices (procurement officer creates and marks paid; admin and vendors view)
# ===========================================================================

@app.route("/invoices")
@login_required
def invoices_list():
    if current_user.role not in ("admin", "procurement_officer", "vendor"):
        flash("You do not have access to invoices.", "error")
        return redirect(url_for("dashboard"))

    is_vendor = current_user.role == "vendor"
    sql = f"""
        SELECT i.id, i.invoice_number, po.po_number, v.company_name AS vendor_name,
               i.subtotal_paise, i.tax_rate, i.tax_amount_paise, i.total_amount_paise,
               i.due_date, {INVOICE_STATUS_SQL} AS payment_status
        FROM invoices i
        JOIN purchase_orders po ON po.id = i.purchase_order_id
        JOIN vendors v ON v.id = po.vendor_id
    """
    params = []
    if is_vendor:
        sql += " WHERE po.vendor_id = ?"
        params.append(current_user.vendor_id)
    sql += " ORDER BY i.created_at DESC, i.id DESC"

    db = get_database()
    try:
        invoices = db.execute(sql, params).fetchall()
        ready_orders = []
        if current_user.role == "procurement_officer":
            ready_orders = db.execute(
                """
                SELECT po.id, po.po_number, v.company_name AS vendor_name, po.total_amount_paise
                FROM purchase_orders po
                JOIN vendors v ON v.id = po.vendor_id
                WHERE po.status != 'cancelled'
                  AND NOT EXISTS (SELECT 1 FROM invoices WHERE purchase_order_id = po.id)
                ORDER BY po.created_at DESC, po.id DESC
                """
            ).fetchall()
    finally:
        db.close()

    return render_template(
        "invoices.html",
        invoices=invoices,
        ready_orders=ready_orders,
        default_tax_rate=18,
        default_due_date=_today_plus(30),
    )


@app.route("/invoices/<int:iid>")
@login_required
def invoice_detail(iid):
    if current_user.role not in ("admin", "procurement_officer", "vendor"):
        flash("You do not have access to invoices.", "error")
        return redirect(url_for("dashboard"))

    db = get_database()
    try:
        invoice = db.execute(
            f"""
            SELECT i.id, i.invoice_number, i.subtotal_paise, i.tax_rate, i.tax_amount_paise,
                   i.total_amount_paise, i.invoice_date, i.due_date, i.paid_at,
                   {INVOICE_STATUS_SQL} AS payment_status,
                   po.id AS po_id, po.po_number, po.vendor_id,
                   r.rfq_number,
                   v.company_name AS vendor_name, v.contact_person, v.email AS vendor_email,
                   v.phone, v.gst_number, v.address
            FROM invoices i
            JOIN purchase_orders po ON po.id = i.purchase_order_id
            JOIN quotations q ON q.id = po.quotation_id
            JOIN rfqs r ON r.id = q.rfq_id
            JOIN vendors v ON v.id = po.vendor_id
            WHERE i.id = ?
            """,
            (iid,),
        ).fetchone()

        if invoice is None or (current_user.role == "vendor" and invoice["vendor_id"] != current_user.vendor_id):
            flash("Invoice not found.", "error")
            return redirect(url_for("invoices_list"))

        lines = db.execute(INVOICE_LINES_SQL, (invoice["po_id"],)).fetchall()
    finally:
        db.close()

    return render_template("invoices.html", invoice=invoice, lines=lines)


@app.route("/invoices/create/<int:po_id>", methods=["POST"])
@login_required
def invoice_create(po_id):
    if current_user.role != "procurement_officer":
        flash("Only procurement officers can create invoices.", "error")
        return redirect(url_for("invoices_list"))

    # Validate input (server side; never trust the browser)
    try:
        tax_rate = Decimal((request.form.get("tax_rate") or "").strip())
        if not tax_rate.is_finite() or tax_rate < 0 or tax_rate > 100:
            raise InvalidOperation
    except InvalidOperation:
        flash("Enter a tax rate between 0 and 100.", "error")
        return redirect(url_for("order_detail", oid=po_id))

    try:
        due = date.fromisoformat((request.form.get("due_date") or "").strip())
    except ValueError:
        flash("Enter a valid due date.", "error")
        return redirect(url_for("order_detail", oid=po_id))
    if due < date.today():
        flash("The due date cannot be in the past.", "error")
        return redirect(url_for("order_detail", oid=po_id))

    db = get_database()
    try:
        _begin(db)
        po = db.execute(
            "SELECT id, po_number, total_amount_paise, status FROM purchase_orders WHERE id = ?", (po_id,)
        ).fetchone()
        if po is None:
            db.rollback()
            flash("Purchase order not found.", "error")
            return redirect(url_for("orders_list"))
        if po["status"] == "cancelled":
            db.rollback()
            flash("A cancelled purchase order cannot be invoiced.", "error")
            return redirect(url_for("order_detail", oid=po_id))

        existing = db.execute(
            "SELECT id FROM invoices WHERE purchase_order_id = ?", (po_id,)
        ).fetchone()
        if existing:
            db.rollback()
            flash("An invoice already exists for this purchase order.", "info")
            return redirect(url_for("invoice_detail", iid=existing["id"]))

        # Decimal-safe money: everything in integer paise, tax rounded half-up to the nearest paisa.
        subtotal = int(po["total_amount_paise"])
        tax_amount = int((Decimal(subtotal) * tax_rate / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        total = subtotal + tax_amount

        invoice_number = _next_number(db, "INV", "invoices", "invoice_number")
        iid = db.execute(
            """INSERT INTO invoices
               (invoice_number, purchase_order_id, subtotal_paise, tax_rate, tax_amount_paise,
                total_amount_paise, invoice_date, due_date, payment_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unpaid')""",
            (invoice_number, po_id, subtotal, float(tax_rate), tax_amount, total,
             date.today().isoformat(), due.isoformat()),
        ).lastrowid
        _log(db, "INVOICE_CREATED", "invoice", iid, f"{invoice_number} for {po['po_number']}")
        db.commit()
        flash(f"Invoice {invoice_number} created.", "success")
        return redirect(url_for("invoice_detail", iid=iid))
    except sqlite3.IntegrityError:
        db.rollback()
        flash("An invoice already exists for this purchase order.", "error")
        return redirect(url_for("order_detail", oid=po_id))
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Could not create the invoice: {e}", "error")
        return redirect(url_for("order_detail", oid=po_id))
    finally:
        db.close()


@app.route("/invoices/<int:iid>/mark-paid", methods=["POST"])
@login_required
def invoice_mark_paid(iid):
    if current_user.role != "procurement_officer":
        flash("Only procurement officers can change payment status.", "error")
        return redirect(url_for("invoices_list"))

    db = get_database()
    try:
        _begin(db)
        inv = db.execute("SELECT id, invoice_number, payment_status FROM invoices WHERE id = ?", (iid,)).fetchone()
        if inv is None:
            db.rollback()
            flash("Invoice not found.", "error")
            return redirect(url_for("invoices_list"))
        if inv["payment_status"] == "paid":
            db.rollback()
            flash("This invoice is already marked as paid.", "info")
            return redirect(url_for("invoice_detail", iid=iid))

        db.execute(
            "UPDATE invoices SET payment_status = 'paid', paid_at = ? WHERE id = ? AND payment_status != 'paid'",
            (_now_iso(), iid),
        )
        _log(db, "INVOICE_PAID", "invoice", iid, f"{inv['invoice_number']} marked as paid")
        db.commit()
        flash(f"Invoice {inv['invoice_number']} marked as paid.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Could not update the invoice: {e}", "error")
    finally:
        db.close()

    return redirect(url_for("invoice_detail", iid=iid))



if __name__ == "__main__":
    app.run(debug=False)