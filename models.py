"""Plain-sqlite3 project: tables live in schema.sql. This file only holds the
User object that Flask-Login needs, built from a database row."""
from flask_login import UserMixin


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.role = row["role"]
        self.vendor_id = row["vendor_id"]
        self.active = bool(row["is_active"])
        self.vendor_name = row["vendor_name"]
        self.vendor_status = row["vendor_status"]

    @property
    def is_active(self):
        return self.active

    @property
    def team_label(self):
        """Name of the team this user belongs to, shown in the account menu."""
        if self.role == "vendor" and self.vendor_name:
            return self.vendor_name
        return "ProcureFlow internal team"

    def team_problem(self):
        """Return why this user cannot sign in to a team, or None if they belong to one."""
        if not self.active:
            return "This account is deactivated. Ask your administrator to reactivate it."
        if self.role == "vendor":
            if self.vendor_id is None or self.vendor_name is None:
                return "Your account is not linked to a vendor company yet. Ask the procurement team to link it."
            if self.vendor_status != "active":
                return f"{self.vendor_name} is currently inactive on ProcureFlow. Contact the procurement team."
        return None