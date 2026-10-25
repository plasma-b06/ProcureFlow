-- ProcureFlow SQLite3 Database Schema
-- Database: instance/procureflow.db
-- Always enable foreign keys on every connection:
--   PRAGMA foreign_keys = ON;
-- This file is safe to run repeatedly (CREATE ... IF NOT EXISTS); existing data is preserved.

PRAGMA foreign_keys = ON;

-- ============================================================
-- Table 2: vendors  (created first because users.vendor_id references it)
-- ============================================================
CREATE TABLE IF NOT EXISTS vendors (
    id              INTEGER PRIMARY KEY,
    company_name    TEXT    NOT NULL,
    contact_person  TEXT    NOT NULL,
    email           TEXT    NOT NULL,
    phone           TEXT,
    gst_number      TEXT    UNIQUE,
    address         TEXT,
    status          TEXT    NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'inactive')),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_vendors_company_name ON vendors(company_name);
CREATE INDEX IF NOT EXISTS idx_vendors_status       ON vendors(status);

-- ============================================================
-- Table 1: users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL CHECK (role IN ('admin', 'procurement_officer', 'vendor', 'manager')),
    vendor_id       INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    -- Vendor accounts must be linked to a vendor record
    CHECK (
        (role = 'vendor' AND vendor_id IS NOT NULL)
        OR (role != 'vendor')
    )
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role  ON users(role);

-- ============================================================
-- Table 3: rfqs
-- ============================================================
CREATE TABLE IF NOT EXISTS rfqs (
    id              INTEGER PRIMARY KEY,
    rfq_number      TEXT    NOT NULL UNIQUE,
    title           TEXT    NOT NULL,
    description     TEXT,
    created_by      INTEGER NOT NULL REFERENCES users(id),
    deadline        TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft', 'published', 'closed', 'cancelled')),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_rfqs_status   ON rfqs(status);
CREATE INDEX IF NOT EXISTS idx_rfqs_deadline ON rfqs(deadline);

-- ============================================================
-- Table 4: rfq_items
-- ============================================================
CREATE TABLE IF NOT EXISTS rfq_items (
    id              INTEGER PRIMARY KEY,
    rfq_id          INTEGER NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    item_name       TEXT    NOT NULL,
    description     TEXT,
    quantity        REAL    NOT NULL CHECK (quantity > 0),
    unit            TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_rfq_items_rfq_id ON rfq_items(rfq_id);

-- ============================================================
-- Table 5: rfq_vendors
-- ============================================================
CREATE TABLE IF NOT EXISTS rfq_vendors (
    id              INTEGER PRIMARY KEY,
    rfq_id          INTEGER NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    vendor_id       INTEGER NOT NULL REFERENCES vendors(id),
    invited_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    status          TEXT    NOT NULL DEFAULT 'invited'
                            CHECK (status IN ('invited', 'responded', 'declined', 'expired')),
    UNIQUE (rfq_id, vendor_id)
);

CREATE INDEX IF NOT EXISTS idx_rfq_vendors_vendor_id ON rfq_vendors(vendor_id);
CREATE INDEX IF NOT EXISTS idx_rfq_vendors_rfq_id    ON rfq_vendors(rfq_id);

-- ============================================================
-- Table 6: quotations
-- ============================================================
CREATE TABLE IF NOT EXISTS quotations (
    id                  INTEGER PRIMARY KEY,
    quotation_number    TEXT    NOT NULL UNIQUE,
    rfq_id              INTEGER NOT NULL REFERENCES rfqs(id),
    vendor_id           INTEGER NOT NULL REFERENCES vendors(id),
    total_amount_paise  INTEGER NOT NULL CHECK (total_amount_paise >= 0),
    delivery_days       INTEGER NOT NULL CHECK (delivery_days >= 0),
    remarks             TEXT,
    status              TEXT    NOT NULL DEFAULT 'draft'
                                CHECK (status IN (
                                    'draft', 'submitted', 'shortlisted',
                                    'pending_approval', 'approved', 'rejected'
                                )),
    submitted_at        TEXT,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (rfq_id, vendor_id)
);

CREATE INDEX IF NOT EXISTS idx_quotations_rfq_id    ON quotations(rfq_id);
CREATE INDEX IF NOT EXISTS idx_quotations_vendor_id ON quotations(vendor_id);
CREATE INDEX IF NOT EXISTS idx_quotations_status    ON quotations(status);

-- ============================================================
-- Table 7: quotation_items
-- ============================================================
CREATE TABLE IF NOT EXISTS quotation_items (
    id                  INTEGER PRIMARY KEY,
    quotation_id        INTEGER NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
    rfq_item_id         INTEGER NOT NULL REFERENCES rfq_items(id),
    unit_price_paise    INTEGER NOT NULL CHECK (unit_price_paise >= 0),
    line_total_paise    INTEGER NOT NULL CHECK (line_total_paise >= 0),
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (quotation_id, rfq_item_id)
);

CREATE INDEX IF NOT EXISTS idx_quotation_items_quotation_id ON quotation_items(quotation_id);

-- ============================================================
-- Table 8: approvals
-- ============================================================
CREATE TABLE IF NOT EXISTS approvals (
    id              INTEGER PRIMARY KEY,
    quotation_id    INTEGER NOT NULL REFERENCES quotations(id),
    manager_id      INTEGER NOT NULL REFERENCES users(id),
    decision        TEXT    NOT NULL DEFAULT 'pending'
                            CHECK (decision IN ('pending', 'approved', 'rejected')),
    remarks         TEXT,
    requested_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    decided_at      TEXT,
    -- Rejection requires remarks
    CHECK (
        (decision != 'rejected')
        OR (decision = 'rejected' AND remarks IS NOT NULL AND length(trim(remarks)) > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_approvals_decision ON approvals(decision);

-- ============================================================
-- Table 9: purchase_orders
-- ============================================================
CREATE TABLE IF NOT EXISTS purchase_orders (
    id                  INTEGER PRIMARY KEY,
    po_number           TEXT    NOT NULL UNIQUE,
    quotation_id        INTEGER NOT NULL UNIQUE REFERENCES quotations(id),
    vendor_id           INTEGER NOT NULL REFERENCES vendors(id),
    total_amount_paise  INTEGER NOT NULL CHECK (total_amount_paise >= 0),
    status              TEXT    NOT NULL DEFAULT 'issued'
                                CHECK (status IN ('issued', 'fulfilled', 'cancelled')),
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_purchase_orders_vendor_id ON purchase_orders(vendor_id);

-- ============================================================
-- Table 10: invoices
-- ============================================================
CREATE TABLE IF NOT EXISTS invoices (
    id                  INTEGER PRIMARY KEY,
    invoice_number      TEXT    NOT NULL UNIQUE,
    purchase_order_id   INTEGER NOT NULL UNIQUE REFERENCES purchase_orders(id),
    subtotal_paise      INTEGER NOT NULL CHECK (subtotal_paise >= 0),
    tax_rate            REAL    NOT NULL CHECK (tax_rate >= 0),
    tax_amount_paise    INTEGER NOT NULL CHECK (tax_amount_paise >= 0),
    total_amount_paise  INTEGER NOT NULL CHECK (total_amount_paise >= 0),
    invoice_date        TEXT    NOT NULL,
    due_date            TEXT    NOT NULL,
    payment_status      TEXT    NOT NULL DEFAULT 'unpaid'
                                CHECK (payment_status IN ('unpaid', 'paid', 'overdue')),
    paid_at             TEXT,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    -- Due date must not precede invoice date
    CHECK (due_date >= invoice_date),
    -- Total must equal subtotal + tax
    CHECK (total_amount_paise = subtotal_paise + tax_amount_paise),
    -- Paid invoices must record paid_at
    CHECK (
        (payment_status != 'paid')
        OR (payment_status = 'paid' AND paid_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_invoices_payment_status ON invoices(payment_status);

-- ============================================================
-- Table 11: activity_logs
-- ============================================================
CREATE TABLE IF NOT EXISTS activity_logs (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT    NOT NULL,
    entity_type     TEXT    NOT NULL,
    entity_id       INTEGER,
    details         TEXT,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON activity_logs(created_at);

-- ============================================================
-- Table 12: demo_requests  (added: stores the public "Request a live demo" form)
-- ============================================================
CREATE TABLE IF NOT EXISTS demo_requests (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL,
    company         TEXT    NOT NULL,
    team_size       TEXT    NOT NULL CHECK (team_size IN ('Just me', '2–10', '11–50', '51–200', '200+')),
    message         TEXT,
    status          TEXT    NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'closed')),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_demo_requests_created_at ON demo_requests(created_at);

-- ============================================================
-- Notes
-- ============================================================
-- Monetary values are stored as integer paise (1 INR = 100 paise)
-- to avoid floating-point precision issues.
--
-- Timestamps use ISO 8601 UTC format: YYYY-MM-DDTHH:MM:SSZ
--
-- Cross-table business rules that cannot be expressed purely in
-- SQLite constraints (e.g. quotation.vendor must be invited via
-- rfq_vendors, quotation_items.rfq_item must belong to the same
-- RFQ as the parent quotation, PO only from approved quotations)
-- must be enforced in application logic.