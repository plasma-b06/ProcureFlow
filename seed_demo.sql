-- ============================================================
-- ProcureFlow demo data
-- ------------------------------------------------------------
-- Run once on a fresh database (start the app once so the tables exist, or run schema.sql first):
--   python -c "import sqlite3; c = sqlite3.connect('instance/procureflow.db'); c.executescript(open('seed_demo.sql', encoding='utf-8').read())"
-- Re-running is safe: every insert is INSERT OR IGNORE.
--
-- Logins (all use password  Demo@1234 ; the hash below is a real werkzeug hash, development only):
--   admin@procureflow.demo     admin
--   officer@procureflow.demo   procurement_officer
--   vendor1@procureflow.demo   vendor  (Acme Steel Co.)
--   vendor2@procureflow.demo   vendor  (Stellar Components Pvt Ltd)
--   manager@procureflow.demo   manager
--
-- What the data shows (today in the demo is about 26 Oct 2026):
--   RFQ-2026-0001  Steel and fasteners      closed.   Stellar rejected, Acme approved, PO-0001, INV-0001 OVERDUE
--   RFQ-2026-0002  Lubricants and coolants  closed.   Stellar approved, PO-0002, INV-0002 PAID
--   RFQ-2026-0003  Hydraulic hoses          open.     Both bids in. Officer can compare and shortlist live
--   RFQ-2026-0004  Safety equipment         open.     Stellar waiting for the manager. Approve live to create a PO
--   RFQ-2026-0005  Packaging material       open.     Both vendors hold empty drafts. Vendor can quote live
--   RFQ-2026-0006  Office furniture         draft.    Officer can publish live
-- Money is stored in paise. Every quotation total equals the sum of its lines.
-- ============================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- ---------- 1. Vendors (matched on GST number) ----------
INSERT OR IGNORE INTO vendors (company_name, contact_person, email, phone, gst_number, address, status, created_at) VALUES
('Acme Steel Co.',             'Rajesh Iyer',  'sales@acmesteel.demo',  '+91 98200 11111', '27AABCA1234F1Z5',
 'Plot 14, MIDC Chinchwad, Pune, Maharashtra 411019',               'active',   '2026-08-12T09:00:00Z'),
('Stellar Components Pvt Ltd', 'Meera Nair',   'quotes@stellar.demo',   '+91 98200 22222', '27AAECS5678K1Z2',
 'Unit 7, Bhosari Industrial Estate, Pune, Maharashtra 411026',     'active',   '2026-08-12T09:10:00Z'),
('Bharat Fasteners & Tools',   'Sunil Kulkarni','orders@bharatfast.demo','+91 98200 33333', '27AAGCB4321H1Z8',
 'Gat 212, Chakan MIDC, Pune, Maharashtra 410501',                  'active',   '2026-08-20T11:00:00Z'),
('Kolhapur Metals',            'Anil Patil',   'info@kolhapurmetals.demo','+91 98200 44444','27AABCK9876L1Z3',
 'Shiroli MIDC, Kolhapur, Maharashtra 416122',                      'inactive', '2026-07-02T10:00:00Z');

-- ---------- 2. Users (matched on email) ----------
INSERT OR IGNORE INTO users (name, email, password_hash, role, vendor_id, is_active, created_at) VALUES
('Asha Admin',     'admin@procureflow.demo',   'scrypt:32768:8:1$pqyuC9nOhDkvRfPc$ddc3a72c0b90775d522d65c01671ffd9884a08376d7658d80339e0e6eca98723d427581236f917010b2e0088c0e80d2016645324f1bf71201749016aff60dcdb', 'admin',               NULL, 1, '2026-08-01T08:00:00Z'),
('Hemant Pande',   'officer@procureflow.demo', 'scrypt:32768:8:1$pqyuC9nOhDkvRfPc$ddc3a72c0b90775d522d65c01671ffd9884a08376d7658d80339e0e6eca98723d427581236f917010b2e0088c0e80d2016645324f1bf71201749016aff60dcdb', 'procurement_officer', NULL, 1, '2026-08-01T08:05:00Z'),
('Marcus Manager', 'manager@procureflow.demo', 'scrypt:32768:8:1$pqyuC9nOhDkvRfPc$ddc3a72c0b90775d522d65c01671ffd9884a08376d7658d80339e0e6eca98723d427581236f917010b2e0088c0e80d2016645324f1bf71201749016aff60dcdb', 'manager',             NULL, 1, '2026-08-01T08:10:00Z');
INSERT OR IGNORE INTO users (name, email, password_hash, role, vendor_id, is_active, created_at) VALUES
('Rajesh Iyer', 'vendor1@procureflow.demo', 'scrypt:32768:8:1$pqyuC9nOhDkvRfPc$ddc3a72c0b90775d522d65c01671ffd9884a08376d7658d80339e0e6eca98723d427581236f917010b2e0088c0e80d2016645324f1bf71201749016aff60dcdb', 'vendor',
 (SELECT id FROM vendors WHERE gst_number = '27AABCA1234F1Z5'), 1, '2026-08-12T09:30:00Z'),
('Meera Nair',  'vendor2@procureflow.demo', 'scrypt:32768:8:1$pqyuC9nOhDkvRfPc$ddc3a72c0b90775d522d65c01671ffd9884a08376d7658d80339e0e6eca98723d427581236f917010b2e0088c0e80d2016645324f1bf71201749016aff60dcdb', 'vendor',
 (SELECT id FROM vendors WHERE gst_number = '27AAECS5678K1Z2'), 1, '2026-08-12T09:40:00Z');

-- Short names for ids that may already exist, so the rows below never depend on guessed ids.
CREATE TEMP TABLE _ref (k TEXT PRIMARY KEY, id INTEGER NOT NULL);
INSERT INTO _ref VALUES
 ('officer', (SELECT id FROM users   WHERE email      = 'officer@procureflow.demo')),
 ('manager', (SELECT id FROM users   WHERE email      = 'manager@procureflow.demo')),
 ('v1user',  (SELECT id FROM users   WHERE email      = 'vendor1@procureflow.demo')),
 ('v2user',  (SELECT id FROM users   WHERE email      = 'vendor2@procureflow.demo')),
 ('acme',    (SELECT id FROM vendors WHERE gst_number = '27AABCA1234F1Z5')),
 ('stellar', (SELECT id FROM vendors WHERE gst_number = '27AAECS5678K1Z2')),
 ('bharat',  (SELECT id FROM vendors WHERE gst_number = '27AAGCB4321H1Z8'));

-- ---------- 3. RFQs ----------
INSERT OR IGNORE INTO rfqs (id, rfq_number, title, description, created_by, deadline, status, created_at, updated_at) VALUES
(1, 'RFQ-2026-0001', 'Structural steel and fasteners',
 'Q3 production line expansion. Quote landed cost, delivered to the Pune plant.',
 (SELECT id FROM _ref WHERE k='officer'), '2026-09-12', 'closed', '2026-09-01T10:00:00Z', '2026-09-16T12:00:00Z'),
(2, 'RFQ-2026-0002', 'Lubricants and coolants',
 'Six-month stock of hydraulic oil, gear oil and coolant for the machine shop.',
 (SELECT id FROM _ref WHERE k='officer'), '2026-10-01', 'closed', '2026-09-20T10:00:00Z', '2026-10-03T12:00:00Z'),
(3, 'RFQ-2026-0003', 'Hydraulic hoses and fittings',
 'Replacement hoses, couplings and gauges for the press line. Delivery to Pune.',
 (SELECT id FROM _ref WHERE k='officer'), '2026-11-20', 'published', '2026-10-18T10:00:00Z', '2026-10-18T10:00:00Z'),
(4, 'RFQ-2026-0004', 'Safety equipment for new shift',
 'PPE for 150 workers joining the third shift. ISI-marked items only.',
 (SELECT id FROM _ref WHERE k='officer'), '2026-11-10', 'published', '2026-10-15T10:00:00Z', '2026-10-15T10:00:00Z'),
(5, 'RFQ-2026-0005', 'Packaging material',
 'Corrugated boxes and stretch film for the dispatch bay, monthly supply.',
 (SELECT id FROM _ref WHERE k='officer'), '2026-11-30', 'published', '2026-10-24T10:00:00Z', '2026-10-24T10:00:00Z'),
(6, 'RFQ-2026-0006', 'Office furniture for the new design wing',
 'Ergonomic seating and adjustable desks for 12 people.',
 (SELECT id FROM _ref WHERE k='officer'), '2026-12-05', 'draft', '2026-10-25T10:00:00Z', '2026-10-25T10:00:00Z');

-- ---------- 4. RFQ items ----------
INSERT OR IGNORE INTO rfq_items (id, rfq_id, item_name, description, quantity, unit) VALUES
(1,  1, 'Mild Steel Plates (12 mm)',        'IS 2062 Grade A, 2500 x 1250 mm',        50,   'MT'),
(2,  1, 'High Tensile Bolts M16 x 80',      'Grade 8.8, hot-dip galvanised with nut', 5000, 'pcs'),
(3,  1, 'Welding Electrodes E6013',         '3.15 mm, 5 kg packs',                    200,  'packs'),
(4,  2, 'Hydraulic Oil ISO VG 68',          '210 L drum',                             20,   'drums'),
(5,  2, 'Gear Oil EP 220',                  '210 L drum',                             10,   'drums'),
(6,  2, 'Coolant Concentrate',              '20 L can',                               40,   'cans'),
(7,  3, 'Hydraulic Hose 1/2 inch',          '2-wire braid, 250 bar',                  200,  'm'),
(8,  3, 'Quick Release Coupling',           '1/2 inch BSP, steel',                    60,   'pcs'),
(9,  3, 'Pressure Gauge 0-400 bar',         '63 mm dial, bottom entry',               25,   'pcs'),
(10, 4, 'Safety Helmet',                    'ISI marked, ratchet suspension',         150,  'pcs'),
(11, 4, 'Safety Shoes',                     'Steel toe, sizes 6 to 11',               150,  'pairs'),
(12, 4, 'Hi-vis Jacket',                    'Reflective, orange',                     150,  'pcs'),
(13, 5, 'Corrugated Box 450 x 300 x 250',   '5-ply, printed',                         2000, 'pcs'),
(14, 5, 'Stretch Film 500 mm',              '23 micron, 2.5 kg roll',                 300,  'rolls'),
(15, 6, 'Ergonomic Office Chair',           'Mesh back, lumbar support, adjustable',  12,   'pcs'),
(16, 6, 'Height-adjustable Desk',           '1400 x 700 mm, electric',                12,   'pcs');

-- ---------- 5. Vendor invitations ----------
INSERT OR IGNORE INTO rfq_vendors (rfq_id, vendor_id, invited_at, status) VALUES
(1, (SELECT id FROM _ref WHERE k='acme'),    '2026-09-02T09:00:00Z', 'responded'),
(1, (SELECT id FROM _ref WHERE k='stellar'), '2026-09-02T09:00:00Z', 'responded'),
(2, (SELECT id FROM _ref WHERE k='acme'),    '2026-09-21T09:00:00Z', 'responded'),
(2, (SELECT id FROM _ref WHERE k='stellar'), '2026-09-21T09:00:00Z', 'responded'),
(3, (SELECT id FROM _ref WHERE k='acme'),    '2026-10-18T10:30:00Z', 'responded'),
(3, (SELECT id FROM _ref WHERE k='stellar'), '2026-10-18T10:30:00Z', 'responded'),
(4, (SELECT id FROM _ref WHERE k='acme'),    '2026-10-15T10:30:00Z', 'responded'),
(4, (SELECT id FROM _ref WHERE k='stellar'), '2026-10-15T10:30:00Z', 'responded'),
(5, (SELECT id FROM _ref WHERE k='acme'),    '2026-10-24T10:30:00Z', 'invited'),
(5, (SELECT id FROM _ref WHERE k='stellar'), '2026-10-24T10:30:00Z', 'invited'),
(6, (SELECT id FROM _ref WHERE k='acme'),    '2026-10-25T10:30:00Z', 'invited'),
(6, (SELECT id FROM _ref WHERE k='bharat'),  '2026-10-25T10:30:00Z', 'invited');

-- ---------- 6. Quotations (amounts in paise; total = sum of its lines) ----------
INSERT OR IGNORE INTO quotations
 (id, quotation_number, rfq_id, vendor_id, total_amount_paise, delivery_days, remarks, status, submitted_at, created_at, updated_at) VALUES
-- RFQ 1: Acme wins after Stellar is rejected
(1,  'QTN-2026-0001', 1, (SELECT id FROM _ref WHERE k='acme'),    311400000, 21,
 'Prices valid for 30 days. Delivery within 3 weeks of the purchase order.', 'approved',
 '2026-09-08T10:30:00Z', '2026-09-02T09:00:00Z', '2026-09-16T11:30:00Z'),
(2,  'QTN-2026-0002', 1, (SELECT id FROM _ref WHERE k='stellar'), 318300000, 18,
 'Faster delivery. Free freight within Maharashtra.', 'rejected',
 '2026-09-09T14:15:00Z', '2026-09-02T09:00:00Z', '2026-09-14T10:00:00Z'),
-- RFQ 2: Stellar wins
(3,  'QTN-2026-0003', 2, (SELECT id FROM _ref WHERE k='acme'),     92000000, 10,
 'Delivery in two lots.', 'submitted',
 '2026-09-28T11:00:00Z', '2026-09-21T09:00:00Z', '2026-09-28T11:00:00Z'),
(4,  'QTN-2026-0004', 2, (SELECT id FROM _ref WHERE k='stellar'),  89400000, 7,
 'Includes drum return at no charge.', 'approved',
 '2026-09-29T15:20:00Z', '2026-09-21T09:00:00Z', '2026-10-03T11:00:00Z'),
-- RFQ 3: both submitted, ready to compare and shortlist
(5,  'QTN-2026-0005', 3, (SELECT id FROM _ref WHERE k='acme'),     21025000, 10,
 'Stock available. Ex-works Pune.', 'submitted',
 '2026-10-22T10:00:00Z', '2026-10-18T10:30:00Z', '2026-10-22T10:00:00Z'),
(6,  'QTN-2026-0006', 3, (SELECT id FROM _ref WHERE k='stellar'),  20490000, 12,
 'Gauges are calibrated and certified.', 'submitted',
 '2026-10-23T13:40:00Z', '2026-10-18T10:30:00Z', '2026-10-23T13:40:00Z'),
-- RFQ 4: Stellar shortlisted, waiting for the manager
(7,  'QTN-2026-0007', 4, (SELECT id FROM _ref WHERE k='acme'),     25125000, 7,
 'Fastest delivery.', 'submitted',
 '2026-10-20T09:30:00Z', '2026-10-15T10:30:00Z', '2026-10-20T09:30:00Z'),
(8,  'QTN-2026-0008', 4, (SELECT id FROM _ref WHERE k='stellar'),  24675000, 15,
 'Lowest price. Delivery in 15 days.', 'pending_approval',
 '2026-10-21T16:10:00Z', '2026-10-15T10:30:00Z', '2026-10-24T09:00:00Z'),
-- RFQ 5: empty drafts waiting for the vendors
(9,  'QTN-2026-0009', 5, (SELECT id FROM _ref WHERE k='acme'),             0, 0, NULL, 'draft', NULL,
 '2026-10-24T10:30:00Z', '2026-10-24T10:30:00Z'),
(10, 'QTN-2026-0010', 5, (SELECT id FROM _ref WHERE k='stellar'),          0, 0, NULL, 'draft', NULL,
 '2026-10-24T10:30:00Z', '2026-10-24T10:30:00Z');

-- ---------- 7. Quotation lines: unit price x quantity = line total ----------
INSERT OR IGNORE INTO quotation_items (quotation_id, rfq_item_id, unit_price_paise, line_total_paise) VALUES
-- QTN-0001 Acme, RFQ 1: 50 x 58,000 + 5,000 x 22 + 200 x 520 = 31,14,000.00
(1, 1, 5800000, 290000000), (1, 2, 2200, 11000000), (1, 3, 52000, 10400000),
-- QTN-0002 Stellar, RFQ 1: 50 x 59,500 + 5,000 x 20 + 200 x 540 = 31,83,000.00
(2, 1, 5950000, 297500000), (2, 2, 2000, 10000000), (2, 3, 54000, 10800000),
-- QTN-0003 Acme, RFQ 2: 20 x 25,200 + 10 x 28,400 + 40 x 3,300 = 9,20,000.00
(3, 4, 2520000, 50400000), (3, 5, 2840000, 28400000), (3, 6, 330000, 13200000),
-- QTN-0004 Stellar, RFQ 2: 20 x 24,500 + 10 x 27,800 + 40 x 3,150 = 8,94,000.00
(4, 4, 2450000, 49000000), (4, 5, 2780000, 27800000), (4, 6, 315000, 12600000),
-- QTN-0005 Acme, RFQ 3: 200 x 640 + 60 x 850 + 25 x 1,250 = 2,10,250.00
(5, 7, 64000, 12800000), (5, 8, 85000, 5100000), (5, 9, 125000, 3125000),
-- QTN-0006 Stellar, RFQ 3: 200 x 610 + 60 x 890 + 25 x 1,180 = 2,04,900.00
(6, 7, 61000, 12200000), (6, 8, 89000, 5340000), (6, 9, 118000, 2950000),
-- QTN-0007 Acme, RFQ 4: 150 x 285 + 150 x 1,150 + 150 x 240 = 2,51,250.00
(7, 10, 28500, 4275000), (7, 11, 115000, 17250000), (7, 12, 24000, 3600000),
-- QTN-0008 Stellar, RFQ 4: 150 x 310 + 150 x 1,080 + 150 x 255 = 2,46,750.00
(8, 10, 31000, 4650000), (8, 11, 108000, 16200000), (8, 12, 25500, 3825000),
-- QTN-0009 / 0010: drafts, no prices yet
(9, 13, 0, 0), (9, 14, 0, 0), (10, 13, 0, 0), (10, 14, 0, 0);

-- ---------- 8. Approvals ----------
INSERT OR IGNORE INTO approvals (id, quotation_id, manager_id, decision, remarks, requested_at, decided_at) VALUES
(1, 2, (SELECT id FROM _ref WHERE k='manager'), 'rejected',
 'Higher total than the other bid and the 3 days saved are not worth the extra cost. Please send the lower bid.',
 '2026-09-13T09:00:00Z', '2026-09-14T10:00:00Z'),
(2, 1, (SELECT id FROM _ref WHERE k='manager'), 'approved',
 'Lowest total and an acceptable lead time. Proceed with the purchase order.',
 '2026-09-15T09:00:00Z', '2026-09-16T11:30:00Z'),
(3, 4, (SELECT id FROM _ref WHERE k='manager'), 'approved',
 'Best price and shortest delivery. Approved.',
 '2026-10-02T09:00:00Z', '2026-10-03T11:00:00Z'),
(4, 8, (SELECT id FROM _ref WHERE k='manager'), 'pending', NULL,
 '2026-10-24T09:00:00Z', NULL);

-- ---------- 9. Purchase orders ----------
INSERT OR IGNORE INTO purchase_orders (id, po_number, quotation_id, vendor_id, total_amount_paise, status, created_at, updated_at) VALUES
(1, 'PO-2026-0001', 1, (SELECT id FROM _ref WHERE k='acme'),    311400000, 'issued',    '2026-09-16T11:30:00Z', '2026-09-16T11:30:00Z'),
(2, 'PO-2026-0002', 4, (SELECT id FROM _ref WHERE k='stellar'),  89400000, 'fulfilled', '2026-10-03T11:00:00Z', '2026-10-10T09:00:00Z');

-- ---------- 10. Invoices (18% GST; tax is rounded to the nearest paisa) ----------
INSERT OR IGNORE INTO invoices
 (id, invoice_number, purchase_order_id, subtotal_paise, tax_rate, tax_amount_paise, total_amount_paise,
  invoice_date, due_date, payment_status, paid_at, created_at) VALUES
-- Unpaid and past its due date, so the app shows it as OVERDUE
(1, 'INV-2026-0001', 1, 311400000, 18.0, 56052000, 367452000,
 '2026-09-24', '2026-10-24', 'unpaid', NULL, '2026-09-24T10:00:00Z'),
-- Paid
(2, 'INV-2026-0002', 2,  89400000, 18.0, 16092000, 105492000,
 '2026-10-05', '2026-11-04', 'paid', '2026-10-10T09:00:00Z', '2026-10-05T10:00:00Z');

-- ---------- 11. Activity log (oldest first) ----------
INSERT OR IGNORE INTO activity_logs (id, user_id, action, entity_type, entity_id, details, created_at) VALUES
(1,  (SELECT id FROM _ref WHERE k='officer'), 'RFQ_CREATED',          'rfq',            1, 'Created RFQ-2026-0001',                       '2026-09-01T10:00:00Z'),
(2,  (SELECT id FROM _ref WHERE k='officer'), 'RFQ_PUBLISHED',        'rfq',            1, 'Published RFQ-2026-0001',                     '2026-09-02T09:00:00Z'),
(3,  (SELECT id FROM _ref WHERE k='v1user'),  'QUOTATION_SUBMITTED',  'quotation',      1, 'Submitted QTN-2026-0001',                     '2026-09-08T10:30:00Z'),
(4,  (SELECT id FROM _ref WHERE k='v2user'),  'QUOTATION_SUBMITTED',  'quotation',      2, 'Submitted QTN-2026-0002',                     '2026-09-09T14:15:00Z'),
(5,  (SELECT id FROM _ref WHERE k='officer'), 'QUOTATION_SHORTLISTED','quotation',      2, 'Shortlisted QTN-2026-0002',                   '2026-09-13T09:00:00Z'),
(6,  (SELECT id FROM _ref WHERE k='manager'), 'QUOTATION_REJECTED',   'quotation',      2, 'Rejected QTN-2026-0002: higher total',        '2026-09-14T10:00:00Z'),
(7,  (SELECT id FROM _ref WHERE k='officer'), 'QUOTATION_SHORTLISTED','quotation',      1, 'Shortlisted QTN-2026-0001',                   '2026-09-15T09:00:00Z'),
(8,  (SELECT id FROM _ref WHERE k='manager'), 'QUOTATION_APPROVED',   'quotation',      1, 'Approved QTN-2026-0001',                      '2026-09-16T11:30:00Z'),
(9,  (SELECT id FROM _ref WHERE k='manager'), 'PO_GENERATED',         'purchase_order', 1, 'PO-2026-0001 from QTN-2026-0001',             '2026-09-16T11:30:00Z'),
(10, (SELECT id FROM _ref WHERE k='officer'), 'INVOICE_CREATED',      'invoice',        1, 'INV-2026-0001 for PO-2026-0001',              '2026-09-24T10:00:00Z'),
(11, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_CREATED',          'rfq',            2, 'Created RFQ-2026-0002',                       '2026-09-20T10:00:00Z'),
(12, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_PUBLISHED',        'rfq',            2, 'Published RFQ-2026-0002',                     '2026-09-21T09:00:00Z'),
(13, (SELECT id FROM _ref WHERE k='v1user'),  'QUOTATION_SUBMITTED',  'quotation',      3, 'Submitted QTN-2026-0003',                     '2026-09-28T11:00:00Z'),
(14, (SELECT id FROM _ref WHERE k='v2user'),  'QUOTATION_SUBMITTED',  'quotation',      4, 'Submitted QTN-2026-0004',                     '2026-09-29T15:20:00Z'),
(15, (SELECT id FROM _ref WHERE k='officer'), 'QUOTATION_SHORTLISTED','quotation',      4, 'Shortlisted QTN-2026-0004',                   '2026-10-02T09:00:00Z'),
(16, (SELECT id FROM _ref WHERE k='manager'), 'QUOTATION_APPROVED',   'quotation',      4, 'Approved QTN-2026-0004',                      '2026-10-03T11:00:00Z'),
(17, (SELECT id FROM _ref WHERE k='manager'), 'PO_GENERATED',         'purchase_order', 2, 'PO-2026-0002 from QTN-2026-0004',             '2026-10-03T11:00:00Z'),
(18, (SELECT id FROM _ref WHERE k='officer'), 'INVOICE_CREATED',      'invoice',        2, 'INV-2026-0002 for PO-2026-0002',              '2026-10-05T10:00:00Z'),
(19, (SELECT id FROM _ref WHERE k='officer'), 'INVOICE_PAID',         'invoice',        2, 'INV-2026-0002 marked as paid',                '2026-10-10T09:00:00Z'),
(20, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_CREATED',          'rfq',            4, 'Created RFQ-2026-0004',                       '2026-10-15T10:00:00Z'),
(21, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_PUBLISHED',        'rfq',            4, 'Published RFQ-2026-0004',                     '2026-10-15T10:30:00Z'),
(22, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_CREATED',          'rfq',            3, 'Created RFQ-2026-0003',                       '2026-10-18T10:00:00Z'),
(23, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_PUBLISHED',        'rfq',            3, 'Published RFQ-2026-0003',                     '2026-10-18T10:30:00Z'),
(24, (SELECT id FROM _ref WHERE k='v1user'),  'QUOTATION_SUBMITTED',  'quotation',      7, 'Submitted QTN-2026-0007',                     '2026-10-20T09:30:00Z'),
(25, (SELECT id FROM _ref WHERE k='v2user'),  'QUOTATION_SUBMITTED',  'quotation',      8, 'Submitted QTN-2026-0008',                     '2026-10-21T16:10:00Z'),
(26, (SELECT id FROM _ref WHERE k='v1user'),  'QUOTATION_SUBMITTED',  'quotation',      5, 'Submitted QTN-2026-0005',                     '2026-10-22T10:00:00Z'),
(27, (SELECT id FROM _ref WHERE k='v2user'),  'QUOTATION_SUBMITTED',  'quotation',      6, 'Submitted QTN-2026-0006',                     '2026-10-23T13:40:00Z'),
(28, (SELECT id FROM _ref WHERE k='officer'), 'QUOTATION_SHORTLISTED','quotation',      8, 'Shortlisted QTN-2026-0008',                   '2026-10-24T09:00:00Z'),
(29, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_CREATED',          'rfq',            5, 'Created RFQ-2026-0005',                       '2026-10-24T10:00:00Z'),
(30, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_PUBLISHED',        'rfq',            5, 'Published RFQ-2026-0005',                     '2026-10-24T10:30:00Z'),
(31, (SELECT id FROM _ref WHERE k='officer'), 'RFQ_CREATED',          'rfq',            6, 'Created RFQ-2026-0006 (draft)',               '2026-10-25T10:00:00Z');

DROP TABLE _ref;

COMMIT;