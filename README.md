# ProcureFlow

**A Flask-Based Vendor Management and Procurement ERP System**

ProcureFlow is a web-based procurement management system designed to simplify vendor registration, Request for Quotation (RFQ) management, quotation comparison, approval workflows, purchase orders, and invoice tracking.

It provides a centralized platform for procurement officers, vendors, managers, and administrators to manage the procurement lifecycle efficiently.

## Features

### 1. User Authentication and Role-Based Access
- Secure login and logout functionality.
- Role-based access for administrators, procurement officers, vendors, and managers.
- Password hashing for secure credential storage.
- Access restrictions based on user roles.

### 2. Vendor Management
- Register and manage vendor profiles.
- Maintain company names, contact details, GST information, and addresses.
- Track vendor status and registration details.
- Allow vendors to access their relevant procurement activities.

### 3. Request for Quotation (RFQ) Management
- Create and manage RFQs.
- Add multiple items with descriptions, quantities, and units.
- Set quotation submission deadlines.
- Publish, close, or cancel RFQs.
- Invite vendors to submit quotations.

### 4. Quotation Management
- Allow vendors to submit quotations against invited RFQs.
- Record item-wise pricing, delivery timelines, and remarks.
- Maintain quotation submission status.
- Prevent duplicate quotations for the same RFQ and vendor, where enforced by the application.

### 5. Quotation Comparison
- Compare vendor quotations side by side.
- Evaluate item-wise prices and total costs.
- Review delivery timelines and vendor responses.
- Shortlist quotations for further approval.

### 6. Approval Workflow
- Send shortlisted quotations for managerial approval.
- Allow managers to approve or reject quotations.
- Record approval decisions and remarks.
- Maintain approval history for tracking procurement decisions.

### 7. Purchase Order Management
- Generate purchase orders from approved quotations.
- Maintain unique purchase order numbers.
- Track purchase order status, including issued, fulfilled, and cancelled orders.

### 8. Invoice and Payment Tracking
- Generate invoices associated with purchase orders.
- Track subtotal, tax, total amount, invoice date, and due date.
- Monitor payment status, including unpaid, paid, and overdue invoices.
- Record payment dates where applicable.

### 9. Dashboard and Activity Logs
- Provide a centralized dashboard for procurement activities.
- Display relevant records and statuses according to the logged-in user's role.
- Maintain activity logs for important system actions, where implemented.

### 10. Responsive User Interface
- Use Bootstrap-based layouts for a clean, responsive interface.
- Provide navigation between procurement modules.
- Use HTML templates, CSS styling, and JavaScript for client-side interactions.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python 3 | Backend programming language |
| Flask | Web application framework |
| HTML5 | Page structure and templates |
| CSS3 | Styling and layout |
| JavaScript | Client-side interactions |
| Bootstrap 5.3 | Responsive UI components |
| SQLite3 | Relational database |
| Flask-SQLAlchemy | Database ORM, if used by the application |
| Flask-Login | User authentication and session management |
| Werkzeug | Password hashing utilities |
| Jinja2 | Dynamic HTML template rendering |
| Bootstrap Icons | Interface icons |

## Project Structure

```text
procureflow/
├── app.py
├── models.py
├── config.py
├── requirements.txt
├── seed_demo.sql
├── instances/
│   └── procureflow.db
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── vendors.html
│   ├── rfqs.html
│   ├── quotations.html
│   ├── approvals.html
│   ├── orders.html
│   └── invoices.html
└── static/
    ├── style.css
    └── app.js
```

*The structure above is illustrative. Actual files and template names may vary depending on the implementation.*

## Prerequisites

Before running ProcureFlow, install:

- Python 3
- pip
- SQLite3 command-line utility
- A terminal or command prompt
- A modern web browser

Verify the installations:

```bash
python3 --version
pip3 --version
sqlite3 --version
```

## Installation and Execution

### Step 1: Open the Project Directory

Navigate to the directory containing the ProcureFlow source code.

```bash
cd procureflow
```

### Step 2: Create the Database Directory

Create the `instances` directory if it does not already exist.

```bash
mkdir -p instances
```

### Step 3: Create the SQLite Database

Create the database file at `instances/procureflow.db`.

```bash
sqlite3 instances/procureflow.db
```

Inside the SQLite prompt, execute:

```sql
.quit
```

Alternatively, create an empty database file directly:

```bash
sqlite3 instances/procureflow.db ".databases"
```

**Important:** The database path in `config.py` or `app.py` must match `instances/procureflow.db`. SQLite can create a database automatically, but its parent directory must already exist.

### Step 4: Create a Virtual Environment

It is recommended to use a virtual environment to isolate project dependencies.

```bash
python3 -m venv .venv
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows Command Prompt:

```bat
.venv\Scripts\activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### Step 5: Install Dependencies

Install the packages listed in `requirements.txt`.

```bash
python3 -m pip install -r requirements.txt
```

If the project uses a virtual environment, ensure it is activated before installing dependencies.

### Step 6: Load Demo Data

ProcureFlow provides a `seed_demo.sql` file containing sample records for demonstration.

Run the following command from the project root:

```bash
sqlite3 instances/procureflow.db < seed_demo.sql
```

This imports the SQL statements and sample data into the database.

The demo data may include:
- Sample users for different roles.
- Vendor profiles.
- RFQs and RFQ items.
- Vendor invitations.
- Submitted quotations.
- Pending and completed approval records.
- Purchase orders.
- Invoices and payment statuses.

**Note:** The SQL seed file must match the database schema expected by the application. If the database is empty, create the required tables first using the project's schema or database initialization process. If the seed file contains only `INSERT` statements, it will not create missing tables.

If you need to reset the demo database, back up any important data before recreating the database and loading the schema and seed data again.

### Step 7: Start the Flask Application

Run the application using:

```bash
python3 app.py
```

If the project exposes a Flask application through the Flask CLI instead, use:

```bash
flask --app app run --debug
```

Use the command appropriate for the project's entry point. Avoid running both commands simultaneously.

### Step 8: Open ProcureFlow

Open your browser and visit:

```text
http://127.0.0.1:5000
```

Log in using one of the demo accounts provided by the project.

## Demo Login Credentials

Use the sample credentials defined in `seed_demo.sql` or in the project's demo documentation.

| Role | Purpose |
|---|---|
| Administrator | Manage system users and oversee the application |
| Procurement Officer | Create RFQs, invite vendors, compare quotations, and manage procurement |
| Vendor | View invitations and submit quotations |
| Manager | Review quotations and approve or reject procurement requests |

**Security note:** Do not assume that the SQL seed file's stored password values are plain-text passwords. If passwords are stored as Werkzeug hashes, use the corresponding demo passwords supplied by the project author. Change demo credentials before deploying the application outside a local demonstration environment.

## Typical Procurement Workflow

1. Log in as a procurement officer.
2. Register or review vendor records.
3. Create an RFQ and add the required items.
4. Publish the RFQ and invite vendors.
5. Log in as a vendor and submit a quotation.
6. Compare the quotations and shortlist a suitable vendor.
7. Log in as a manager to approve or reject the shortlisted quotation.
8. Generate a purchase order from an approved quotation.
9. Create an invoice and update its payment status.
10. Review the dashboard and activity history.

## Useful Database Commands

**View the database tables:**

```bash
sqlite3 instances/procureflow.db ".tables"
```

**Open the database interactively:**

```bash
sqlite3 instances/procureflow.db
```

**View the table schema:**

```sql
.schema
```

**Inspect sample users:**

```sql
SELECT id, name, email, role
FROM users;
```

**Exit SQLite:**

```sql
.quit
```

The SQL examples assume the database uses a `users` table with the listed columns.

## Troubleshooting

### `sqlite3: command not found`

Install the SQLite command-line utility and ensure it is available on your system's PATH.

### `no such table` Error

The required schema has not been created, or the seed file targets a different schema. Initialize the tables before importing the demo data.

### `no such file or directory`

Confirm that you are running commands from the project root and that the `instances` directory exists.

### Flask Cannot Find the Database

Check the database path in `config.py` or `app.py`. Ensure that it points to the same `instances/procureflow.db` file used when loading the seed data.

### Login Does Not Work

Check the demo email addresses and password values provided with the project. Confirm that the application's password verification method matches the way passwords were seeded.

### Port 5000 Is Already in Use

Start the application on another port:

```bash
flask --app app run --port 5001
```

Then visit `http://127.0.0.1:5001`.

## Security Considerations

- Store passwords using secure password hashing.
- Enforce role permissions on the server, not just in the interface.
- Validate form inputs and database operations.
- Enable SQLite foreign-key enforcement where required.
- Protect state-changing forms against CSRF attacks if supported by the application.
- Do not use the Flask debug server as a production deployment server.
- Never use demonstration credentials or development settings in a production environment.

## Future Enhancements

Possible future improvements include:

- PDF export for quotations, purchase orders, and invoices.
- Email notifications for RFQ deadlines and approval decisions.
- Advanced procurement analytics and reports.
- Vendor performance scoring.
- CSV export for reports.
- Improved audit trails and configurable approval policies.

## License

This project is intended for educational, demonstration, and hackathon use unless a separate license specifies otherwise.

---

**ProcureFlow — Simplifying vendor management and procurement through a unified workflow.**
