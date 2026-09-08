# Bryan Pham | Austin Nguyenminh
# #1002120409| #1002097413

import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import mysql.connector


app = FastAPI(
    title="APC Records API",
    description=(
        "Ambulatory Patient Care database API. Browse tables in your browser "
        "at `/`, or use the endpoints below to read, add, and modify records "
        "directly (e.g. from Postman, curl, or this Swagger page)."
    ),
    version="1.1.0",
)

DB_NAME = "apc_db"


def get_conn():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database=DB_NAME,
    )


# Tables exposed in the dashboard, and the only tables the API will read
# from or write to. Keeping this whitelist means a typo or a bad table
# name in a request fails with a clear error instead of a raw MySQL error,
# and it stops arbitrary table names from being queried.
TABLES = [
    "patient",
    "physician",
    "consultation",
    "hospital",
    "hospital_location",
    "diagnosis",
    "coveragepolicy",
    "speciality",
    "physician_speciality",
]

# Plain-language subtitle for each table, shown on the dashboard so
# non-technical users know what they're clicking into.
TABLE_DESCRIPTIONS = {
    "patient": "People receiving care",
    "physician": "Doctors on staff",
    "consultation": "Visits between a patient and a physician",
    "hospital": "Hospital locations in the network",
    "hospital_location": "Addresses and sites for each hospital",
    "diagnosis": "Diagnoses recorded during a visit",
    "coveragepolicy": "Insurance coverage policies",
    "speciality": "Medical specialities",
    "physician_speciality": "Which physicians practice which specialities",
}


def validate_table(table_name: str) -> None:
    if table_name not in TABLES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown table '{table_name}'. "
                f"Valid tables are: {', '.join(TABLES)}"
            ),
        )


def table_row_count(table_name: str) -> Optional[int]:
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cur.fetchone()[0]
    except mysql.connector.Error:
        return None
    finally:
        if conn is not None:
            conn.close()


def table_primary_key(table_name: str) -> Optional[str]:
    """Looks up the real primary key column from MySQL itself, rather than
    guessing from the column name, so Edit/Delete target the right row."""
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY'
            ORDER BY ORDINAL_POSITION
            """,
            (DB_NAME, table_name),
        )
        rows = cur.fetchall()
        return rows[0][0] if rows else None
    except mysql.connector.Error:
        return None
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Column validation
#
# Two layers of rules feed the same schema:
#   1. Pattern rules below, matched against the column NAME (e.g. any
#      column with "ssn" in it must look like a Social Security Number).
#   2. Fallback rules based on the column's actual MySQL DATA TYPE, so
#      numeric columns require numbers and date columns require real
#      dates even if there's no name-based rule for them.
# The same schema is sent to the browser (so bad input is caught before
# it's ever submitted) and re-checked on the server (so the rule can't
# be bypassed by calling the API directly).
# ---------------------------------------------------------------------------

FIELD_NAME_RULES = [
    (re.compile(r"ssn", re.I), r"^\d{3}-?\d{2}-?\d{4}$", "Must be a Social Security Number, e.g. 123-45-6789."),
    (re.compile(r"email", re.I), r"^[^@\s]+@[^@\s]+\.[^@\s]+$", "Must be a valid email address."),
    (re.compile(r"phone", re.I), r"^\d{3}-?\d{3}-?\d{4}$", "Must be a 10-digit phone number, e.g. 555-123-4567."),
    (re.compile(r"^sex$", re.I), r"^[MFmf]$", "Must be M or F."),
    (re.compile(r"zip", re.I), r"^\d{5}(-\d{4})?$", "Must be a 5-digit ZIP code."),
]

NUMERIC_TYPES = {"int", "tinyint", "smallint", "mediumint", "bigint", "decimal", "float", "double"}
DATE_TYPES = {"date"}
DATETIME_TYPES = {"datetime", "timestamp"}


def _find_name_rule(column_name: str):
    for pattern, regex, message in FIELD_NAME_RULES:
        if pattern.search(column_name):
            return regex, message
    return None, None


def get_table_schema(table_name: str) -> List[Dict[str, Any]]:
    """Combines MySQL's own column types with the name-based rules above
    into one list the frontend can render inputs from and the backend can
    re-validate against."""
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (DB_NAME, table_name),
        )
        columns = []
        for name, data_type, is_nullable, max_len in cur.fetchall():
            regex, message = _find_name_rule(name)
            input_type = "text"
            if regex is None:
                if data_type in NUMERIC_TYPES:
                    input_type = "number"
                    regex = r"^-?\d+(\.\d+)?$"
                    message = "Must be a number."
                elif data_type in DATE_TYPES:
                    input_type = "date"
                elif data_type in DATETIME_TYPES:
                    input_type = "datetime-local"
            columns.append(
                {
                    "name": name,
                    "data_type": data_type,
                    "input_type": input_type,
                    "required": is_nullable == "NO",
                    "max_length": max_len,
                    "pattern": regex,
                    "message": message,
                }
            )
        return columns
    except mysql.connector.Error:
        return []
    finally:
        if conn is not None:
            conn.close()


def validate_row_against_schema(table_name: str, data: Dict[str, Any]) -> Dict[str, str]:
    """Server-side re-check of the same rules the browser enforces, so the
    API can't be used to sneak in bad values even if someone bypasses the
    web form (e.g. calling /api/table/... directly)."""
    schema = {col["name"]: col for col in get_table_schema(table_name)}
    errors: Dict[str, str] = {}
    for col, value in data.items():
        info = schema.get(col)
        if not info:
            continue  # unknown column name — let MySQL raise its own error
        if value in (None, ""):
            if info["required"]:
                errors[col] = "This field is required."
            continue
        if info["pattern"] and not re.match(info["pattern"], str(value)):
            errors[col] = info["message"] or f"Invalid value for {col}."
    return errors


# ---------------------------------------------------------------------------
# Referential integrity (foreign keys)
#
# This reads whatever foreign key constraints actually exist in MySQL
# (information_schema), so it automatically picks up every relationship
# from your ER diagram once the constraints are added with the .sql script
# — no table names are hardcoded here. Two things come from this:
#   1. Before an insert/update, we check the referenced row actually
#      exists and give a plain-English error immediately.
#   2. If MySQL itself blocks something (e.g. because ON DELETE RESTRICT
#      stopped a delete that would orphan child rows), we translate that
#      raw error into a readable message instead of a MySQL error code.
# The actual "update a table and its related tables stay in sync" behavior
# comes from ON UPDATE CASCADE on these constraints in MySQL itself — see
# the accompanying add_foreign_keys.sql.
# ---------------------------------------------------------------------------

def get_foreign_keys(table_name: str) -> List[Dict[str, str]]:
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            (DB_NAME, table_name),
        )
        return [
            {"column": c, "referenced_table": rt, "referenced_column": rc}
            for c, rt, rc in cur.fetchall()
        ]
    except mysql.connector.Error:
        return []
    finally:
        if conn is not None:
            conn.close()


def validate_foreign_keys(table_name: str, data: Dict[str, Any]) -> Dict[str, str]:
    """Checks each foreign-key column in `data` against its parent table.
    Note: for a composite foreign key (multiple columns together, e.g.
    diagnosis -> consultation), this checks each column independently as a
    quick heads-up — MySQL's own constraint is still the final, authoritative
    check when the row is actually written."""
    errors: Dict[str, str] = {}
    for fk in get_foreign_keys(table_name):
        col = fk["column"]
        if col not in data or data[col] in (None, ""):
            continue
        conn = None
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                f"SELECT 1 FROM {fk['referenced_table']} WHERE {fk['referenced_column']} = %s LIMIT 1",
                (data[col],),
            )
            if cur.fetchone() is None:
                errors[col] = (
                    f"No matching record in '{fk['referenced_table']}' where "
                    f"{fk['referenced_column']} = {data[col]!r}."
                )
        except mysql.connector.Error:
            pass
        finally:
            if conn is not None:
                conn.close()
    return errors


def friendly_db_error(e: "mysql.connector.Error") -> str:
    """Turns common MySQL error codes into plain English."""
    errno = getattr(e, "errno", None)
    if errno == 1452:
        return (
            "That value doesn't match any existing record in the table it's "
            "linked to. Double-check the ID you entered exists there first."
        )
    if errno == 1451:
        return (
            "This record is still referenced by other tables (for example, "
            "consultations or diagnoses). Update or remove those first before "
            "changing or deleting this one."
        )
    if errno == 1062:
        return "A record with this value already exists — it must be unique."
    if errno == 1048:
        return "This field can't be left empty."
    return str(e)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class RowData(BaseModel):
    """Column name -> value pairs for one row."""
    data: Dict[str, Any] = Field(
        ...,
        description="Column names mapped to their values.",
        examples=[{"first_name": "Jane", "last_name": "Doe", "dob": "1990-01-01"}],
    )


class QueryPayload(BaseModel):
    query: str = Field(
        ...,
        description="A raw SQL SELECT statement.",
        examples=["SELECT * FROM patient WHERE last_name = 'Doe'"],
    )


class StatusResponse(BaseModel):
    status: str
    row_id: Optional[str] = None


class QueryResponse(BaseModel):
    columns: List[str]
    rows: List[List[Any]]


class TableMeta(BaseModel):
    columns: List[str]
    primary_key: Optional[str]
    rows: List[List[Any]]


# ---------------------------------------------------------------------------
# Shared visual language: a quiet records-ledger look (slate ink, one
# clinical-green accent, serif for reading, monospace for tabular data)
# rather than a generic SaaS dashboard.
# ---------------------------------------------------------------------------

BASE_STYLE = """
    :root {
        --ink: #1C2733;
        --paper: #FAFAF8;
        --panel: #FFFFFF;
        --line: #E1DED6;
        --muted: #6B7280;
        --accent: #3E6D5C;
        --accent-soft: #E9EFEC;
        --danger: #A6423A;
        --danger-soft: #F5E9E8;
    }
    * { box-sizing: border-box; }
    body {
        margin: 0;
        font-family: 'Source Serif 4', Georgia, 'Times New Roman', serif;
        background: var(--paper);
        color: var(--ink);
        display: flex;
        min-height: 100vh;
    }
    a { color: var(--accent); }
    .sidebar {
        width: 240px;
        flex-shrink: 0;
        background: var(--panel);
        border-right: 1px solid var(--line);
        padding: 32px 24px;
    }
    .sidebar .brand {
        font-size: 13px;
        letter-spacing: 0.02em;
        color: var(--muted);
        margin: 0 0 4px;
    }
    .sidebar h2 {
        font-size: 20px;
        margin: 0 0 28px;
        line-height: 1.3;
    }
    .sidebar nav ul {
        list-style: none;
        margin: 0;
        padding: 0;
    }
    .sidebar nav li + li { margin-top: 2px; }
    .sidebar nav a {
        display: block;
        padding: 7px 10px;
        margin: 0 -10px;
        border-radius: 4px;
        text-decoration: none;
        font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
        font-size: 13px;
        color: var(--ink);
        border-left: 2px solid transparent;
    }
    .sidebar nav a:hover {
        background: var(--accent-soft);
        border-left-color: var(--accent);
        color: var(--accent);
    }
    .sidebar nav a.active {
        background: var(--accent-soft);
        border-left-color: var(--accent);
        color: var(--accent);
    }
    .sidebar .docs-link {
        display: inline-block;
        margin-top: 32px;
        font-size: 13px;
        color: var(--muted);
        text-decoration: none;
        border-bottom: 1px solid var(--line);
    }
    .sidebar .docs-link:hover { color: var(--accent); border-color: var(--accent); }
    main {
        flex: 1;
        padding: 48px 56px;
        max-width: 1200px;
    }
    main h1 {
        font-size: 30px;
        margin: 0 0 8px;
        font-weight: 600;
    }
    main .lede {
        color: var(--muted);
        font-size: 16px;
        margin: 0 0 32px;
        max-width: 60ch;
    }
    button {
        font-family: inherit;
        cursor: pointer;
    }
"""

# Styles specific to the dashboard's table cards.
HOME_STYLE = """
    .card-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
        gap: 16px;
    }
    .table-card {
        display: flex;
        gap: 14px;
        align-items: flex-start;
        text-decoration: none;
        color: var(--ink);
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 18px;
        transition: border-color 0.15s ease;
    }
    .table-card:hover {
        border-color: var(--accent);
    }
    .table-card .monogram {
        flex-shrink: 0;
        width: 40px;
        height: 40px;
        border-radius: 6px;
        background: var(--accent-soft);
        color: var(--accent);
        font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
        font-weight: 500;
        font-size: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .table-card h3 {
        margin: 0 0 4px;
        font-size: 16px;
        font-weight: 600;
    }
    .table-card p {
        margin: 0 0 8px;
        font-size: 13px;
        color: var(--muted);
        line-height: 1.4;
    }
    .table-card .count {
        font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
        font-size: 12px;
        color: var(--accent);
    }
"""

# Styles specific to the record-browser (search bar, table, modal, toast).
TABLE_PAGE_STYLE = """
    .toolbar {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 20px;
    }
    .toolbar input[type="search"] {
        flex: 1;
        max-width: 320px;
        padding: 9px 12px;
        border: 1px solid var(--line);
        border-radius: 6px;
        font-family: inherit;
        font-size: 14px;
        background: var(--panel);
        color: var(--ink);
    }
    .toolbar input[type="search"]:focus {
        outline: 2px solid var(--accent);
        outline-offset: 1px;
    }
    .btn {
        border: 1px solid var(--accent);
        background: var(--accent);
        color: #fff;
        padding: 9px 16px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 500;
    }
    .btn:hover { opacity: 0.9; }
    .btn-secondary {
        border: 1px solid var(--line);
        background: var(--panel);
        color: var(--ink);
    }
    .btn-secondary:hover { border-color: var(--accent); color: var(--accent); }
    .btn-text {
        border: none;
        background: none;
        padding: 4px 8px;
        font-size: 13px;
        color: var(--accent);
        text-decoration: underline;
    }
    .btn-text.danger { color: var(--danger); }
    .meta {
        font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
        font-size: 12px;
        color: var(--muted);
        margin: 0 0 16px;
    }
    .table-wrap {
        border: 1px solid var(--line);
        border-radius: 6px;
        overflow: auto;
        background: var(--panel);
        max-height: 70vh;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
        font-size: 13px;
    }
    th, td {
        padding: 10px 16px;
        border-bottom: 1px solid var(--line);
        text-align: left;
        white-space: nowrap;
    }
    thead th {
        background: var(--accent-soft);
        color: var(--accent);
        font-weight: 500;
        border-bottom: 1px solid var(--line);
        position: sticky;
        top: 0;
    }
    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover { background: var(--accent-soft); }
    td.actions { white-space: nowrap; }
    .empty-state, .loading-state, .error-state {
        padding: 40px 20px;
        text-align: center;
        color: var(--muted);
        font-size: 14px;
    }
    .error-state { color: var(--danger); }

    /* Modal */
    .modal-backdrop {
        display: none;
        position: fixed;
        inset: 0;
        background: rgba(28, 39, 51, 0.4);
        align-items: center;
        justify-content: center;
        z-index: 50;
    }
    .modal-backdrop.open { display: flex; }
    .modal {
        background: var(--panel);
        border-radius: 10px;
        width: 460px;
        max-width: calc(100vw - 32px);
        max-height: calc(100vh - 64px);
        overflow-y: auto;
        padding: 28px;
    }
    .modal h2 {
        margin: 0 0 4px;
        font-size: 19px;
    }
    .modal .modal-sub {
        margin: 0 0 20px;
        font-size: 13px;
        color: var(--muted);
    }
    .field { margin-bottom: 14px; }
    .field label {
        display: block;
        font-size: 12px;
        font-weight: 500;
        color: var(--muted);
        margin-bottom: 5px;
        font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
    }
    .field input {
        width: 100%;
        padding: 8px 10px;
        border: 1px solid var(--line);
        border-radius: 5px;
        font-family: inherit;
        font-size: 14px;
        background: var(--paper);
        color: var(--ink);
    }
    .field input:disabled {
        color: var(--muted);
        background: var(--line);
    }
    .field input:focus {
        outline: 2px solid var(--accent);
        outline-offset: 1px;
    }
    .field input:invalid:not(:placeholder-shown) {
        border-color: var(--danger);
    }
    .field-hint {
        display: block;
        font-size: 11px;
        color: var(--muted);
        margin-top: 4px;
    }
    .modal-actions {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 22px;
    }
    .modal-error {
        display: none;
        background: var(--danger-soft);
        color: var(--danger);
        border-radius: 6px;
        padding: 10px 12px;
        font-size: 13px;
        margin-bottom: 14px;
    }
    .modal-error.show { display: block; }

    /* Toast */
    .toast {
        position: fixed;
        bottom: 24px;
        right: 24px;
        background: var(--ink);
        color: #fff;
        padding: 12px 18px;
        border-radius: 6px;
        font-size: 14px;
        opacity: 0;
        transform: translateY(8px);
        transition: opacity 0.2s ease, transform 0.2s ease;
        z-index: 100;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
    .toast.danger { background: var(--danger); }
"""


def render_sidebar(active_table: Optional[str] = None) -> str:
    nav_items = "".join(
        f'<li><a class="{"active" if t == active_table else ""}" '
        f'href="/table/{t}">{t.replace("_", " ").title()}</a></li>'
        for t in TABLES
    )
    return f"""
        <p class="brand">APC Records</p>
        <h2>Table Index</h2>
        <nav><ul>{nav_items}</ul></nav>
        <a class="docs-link" href="/docs">Developer / API docs &rarr;</a>
    """


# ---------------------------------------------------------------------------
# Browser pages (HTML)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["Pages"], summary="Home / table dashboard")
def home():
    cards = ""
    for t in TABLES:
        count = table_row_count(t)
        count_label = f"{count} record{'s' if count != 1 else ''}" if count is not None else "—"
        monogram = t[0].upper()
        description = TABLE_DESCRIPTIONS.get(t, "")
        cards += f"""
        <a class="table-card" href="/table/{t}">
            <div class="monogram">{monogram}</div>
            <div>
                <h3>{t.replace("_", " ").title()}</h3>
                <p>{description}</p>
                <span class="count">{count_label}</span>
            </div>
        </a>
        """

    return f"""
    <html>
        <head>
            <title>APC Records</title>
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
            <style>{BASE_STYLE}{HOME_STYLE}</style>
        </head>
        <body>
            <aside class="sidebar">{render_sidebar()}</aside>
            <main>
                <h1>Ambulatory Patient Care</h1>
                <p class="lede">Pick a table below to view, search, add, or edit its records.</p>
                <div class="card-grid">{cards}</div>
            </main>
        </body>
    </html>
    """


@app.get(
    "/table/{table_name}",
    response_class=HTMLResponse,
    tags=["Pages"],
    summary="Browse, search, add, edit, and delete records in a table",
)
def get_table(table_name: str):
    validate_table(table_name)
    title = table_name.replace("_", " ").title()

    return f"""
    <html>
        <head>
            <title>{title} — APC Records</title>
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
            <style>{BASE_STYLE}{TABLE_PAGE_STYLE}</style>
        </head>
        <body>
            <aside class="sidebar">{render_sidebar(table_name)}</aside>
            <main>
                <h1>{title}</h1>
                <p class="meta" id="rowMeta">Loading&hellip;</p>

                <div class="toolbar">
                    <input type="search" id="searchBox" placeholder="Search {title.lower()}&hellip;">
                    <button class="btn" id="addBtn">+ Add record</button>
                </div>

                <div class="table-wrap">
                    <table id="dataTable" style="display:none;">
                        <thead><tr id="headerRow"></tr></thead>
                        <tbody id="bodyRows"></tbody>
                    </table>
                    <div class="loading-state" id="loadingState">Loading records&hellip;</div>
                    <div class="empty-state" id="emptyState" style="display:none;">
                        No records yet. Click &ldquo;+ Add record&rdquo; to create the first one.
                    </div>
                    <div class="error-state" id="errorState" style="display:none;"></div>
                </div>
            </main>

            <div class="modal-backdrop" id="modalBackdrop">
                <div class="modal">
                    <h2 id="modalTitle">Add record</h2>
                    <p class="modal-sub" id="modalSub">Fill in the fields below.</p>
                    <div class="modal-error" id="modalError"></div>
                    <form id="recordForm"></form>
                    <div class="modal-actions">
                        <button class="btn btn-secondary" type="button" id="cancelBtn">Cancel</button>
                        <button class="btn" type="submit" form="recordForm" id="saveBtn">Save</button>
                    </div>
                </div>
            </div>

            <div class="toast" id="toast"></div>

            <script>
                const TABLE_NAME = {table_name!r};
                let COLUMNS = [];
                let PRIMARY_KEY = null;
                let ROWS = [];
                let SCHEMA = {{}}; // column name -> {{input_type, pattern, required, message, max_length}}
                let EDITING_ID = null; // null = add mode, otherwise the row's primary key value

                const el = (id) => document.getElementById(id);

                function showToast(message, isError) {{
                    const t = el('toast');
                    t.textContent = message;
                    t.className = 'toast show' + (isError ? ' danger' : '');
                    setTimeout(() => {{ t.className = 'toast'; }}, 3000);
                }}

                function humanLabel(col) {{
                    return col.replace(/_/g, ' ').replace(/\\b\\w/g, (c) => c.toUpperCase());
                }}

                async function loadTable() {{
                    el('loadingState').style.display = 'block';
                    el('errorState').style.display = 'none';
                    el('emptyState').style.display = 'none';
                    el('dataTable').style.display = 'none';
                    try {{
                        const [metaRes, dataRes, schemaRes] = await Promise.all([
                            fetch(`/api/table/${{TABLE_NAME}}/meta`),
                            fetch(`/api/table/${{TABLE_NAME}}`),
                            fetch(`/api/table/${{TABLE_NAME}}/schema`),
                        ]);
                        if (!metaRes.ok || !dataRes.ok || !schemaRes.ok) throw new Error('Could not load this table.');
                        const meta = await metaRes.json();
                        const data = await dataRes.json();
                        const schema = await schemaRes.json();
                        PRIMARY_KEY = meta.primary_key;
                        COLUMNS = data.columns;
                        ROWS = data.rows;
                        SCHEMA = {{}};
                        for (const col of schema.columns) {{ SCHEMA[col.name] = col; }}
                        renderTable(ROWS);
                    }} catch (err) {{
                        el('loadingState').style.display = 'none';
                        el('errorState').style.display = 'block';
                        el('errorState').textContent = err.message || 'Something went wrong loading this table.';
                    }}
                }}

                function renderTable(rows) {{
                    el('loadingState').style.display = 'none';
                    el('rowMeta').textContent = `${{ROWS.length}} record${{ROWS.length !== 1 ? 's' : ''}} · ${{COLUMNS.length}} columns`;

                    if (ROWS.length === 0) {{
                        el('emptyState').style.display = 'block';
                        return;
                    }}
                    if (rows.length === 0) {{
                        el('dataTable').style.display = 'none';
                        el('emptyState').style.display = 'block';
                        el('emptyState').textContent = 'No records match your search.';
                        return;
                    }}
                    el('emptyState').style.display = 'none';
                    el('dataTable').style.display = 'table';

                    el('headerRow').innerHTML = COLUMNS.map(c => `<th>${{humanLabel(c)}}</th>`).join('') + '<th>Actions</th>';

                    el('bodyRows').innerHTML = rows.map(row => {{
                        const cells = row.map(cell => `<td>${{cell === null ? '' : String(cell)}}</td>`).join('');
                        const idIdx = COLUMNS.indexOf(PRIMARY_KEY);
                        const rowId = idIdx >= 0 ? row[idIdx] : null;
                        const actions = rowId !== null
                            ? `<button class="btn-text" onclick="openEdit('${{rowId}}')">Edit</button>` +
                              `<button class="btn-text danger" onclick="deleteRecord('${{rowId}}')">Delete</button>`
                            : '<span style="color:var(--muted); font-size:12px;">no id</span>';
                        return `<tr>${{cells}}<td class="actions">${{actions}}</td></tr>`;
                    }}).join('');
                }}

                el('searchBox').addEventListener('input', (e) => {{
                    const q = e.target.value.trim().toLowerCase();
                    if (!q) {{ renderTable(ROWS); return; }}
                    const filtered = ROWS.filter(row => row.some(cell => String(cell ?? '').toLowerCase().includes(q)));
                    renderTable(filtered);
                }});

                function escapeAttr(v) {{
                    return String(v).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
                }}

                function buildForm(existingRow) {{
                    const form = el('recordForm');
                    form.innerHTML = COLUMNS.map((col, i) => {{
                        const isKey = col === PRIMARY_KEY;
                        const value = existingRow ? (existingRow[i] ?? '') : '';
                        const disabled = (isKey && existingRow) ? 'disabled' : '';
                        const info = SCHEMA[col] || {{}};
                        const type = info.input_type || 'text';
                        const patternAttr = info.pattern ? `pattern="${{escapeAttr(info.pattern)}}"` : '';
                        const requiredAttr = (info.required && !isKey) ? 'required' : '';
                        const maxLenAttr = info.max_length ? `maxlength="${{info.max_length}}"` : '';
                        const hintText = info.message ? info.message : '';
                        return `
                            <div class="field">
                                <label for="f_${{col}}">${{humanLabel(col)}}${{isKey ? ' (ID)' : ''}}</label>
                                <input id="f_${{col}}" name="${{col}}" type="${{type}}"
                                    value="${{escapeAttr(value)}}" ${{disabled}} ${{patternAttr}}
                                    ${{requiredAttr}} ${{maxLenAttr}} title="${{escapeAttr(hintText)}}">
                                ${{hintText ? `<span class="field-hint">${{hintText}}</span>` : ''}}
                            </div>`;
                    }}).join('');
                }}

                function openAdd() {{
                    EDITING_ID = null;
                    el('modalTitle').textContent = 'Add record';
                    el('modalSub').textContent = `New entry in ${{humanLabel(TABLE_NAME)}}.`;
                    el('modalError').className = 'modal-error';
                    buildForm(null);
                    el('modalBackdrop').className = 'modal-backdrop open';
                }}

                function openEdit(rowId) {{
                    const idIdx = COLUMNS.indexOf(PRIMARY_KEY);
                    const row = ROWS.find(r => String(r[idIdx]) === String(rowId));
                    if (!row) return;
                    EDITING_ID = rowId;
                    el('modalTitle').textContent = 'Edit record';
                    el('modalSub').textContent = `Editing ${{humanLabel(PRIMARY_KEY)}} ${{rowId}}.`;
                    el('modalError').className = 'modal-error';
                    buildForm(row);
                    el('modalBackdrop').className = 'modal-backdrop open';
                }}

                function closeModal() {{
                    el('modalBackdrop').className = 'modal-backdrop';
                }}

                el('addBtn').addEventListener('click', openAdd);
                el('cancelBtn').addEventListener('click', closeModal);
                el('modalBackdrop').addEventListener('click', (e) => {{
                    if (e.target === el('modalBackdrop')) closeModal();
                }});

                el('recordForm').addEventListener('submit', async (e) => {{
                    e.preventDefault();
                    const form = e.target;
                    if (!form.checkValidity()) {{
                        form.reportValidity();
                        return;
                    }}
                    const formData = new FormData(e.target);
                    const data = {{}};
                    for (const [key, val] of formData.entries()) {{
                        if (key === PRIMARY_KEY && EDITING_ID !== null) continue; // don't resend disabled id field
                        data[key] = val;
                    }}
                    const errBox = el('modalError');
                    errBox.className = 'modal-error';
                    try {{
                        let res;
                        if (EDITING_ID === null) {{
                            res = await fetch(`/api/table/${{TABLE_NAME}}`, {{
                                method: 'POST',
                                headers: {{'Content-Type': 'application/json'}},
                                body: JSON.stringify({{data}}),
                            }});
                        }} else {{
                            res = await fetch(`/api/table/${{TABLE_NAME}}/${{PRIMARY_KEY}}/${{EDITING_ID}}`, {{
                                method: 'PUT',
                                headers: {{'Content-Type': 'application/json'}},
                                body: JSON.stringify({{data}}),
                            }});
                        }}
                        const body = await res.json();
                        if (!res.ok) throw new Error(body.detail || 'Save failed.');
                        closeModal();
                        showToast(EDITING_ID === null ? 'Record added.' : 'Record updated.', false);
                        loadTable();
                    }} catch (err) {{
                        errBox.textContent = err.message;
                        errBox.className = 'modal-error show';
                    }}
                }});

                async function deleteRecord(rowId) {{
                    if (!confirm(`Delete ${{humanLabel(PRIMARY_KEY)}} ${{rowId}}? This can't be undone.`)) return;
                    try {{
                        const res = await fetch(`/api/table/${{TABLE_NAME}}/${{PRIMARY_KEY}}/${{rowId}}`, {{ method: 'DELETE' }});
                        const body = await res.json();
                        if (!res.ok) throw new Error(body.detail || 'Delete failed.');
                        showToast('Record deleted.', false);
                        loadTable();
                    }} catch (err) {{
                        showToast(err.message, true);
                    }}
                }}

                loadTable();
            </script>
        </body>
    </html>
    """


# ---------------------------------------------------------------------------
# JSON API (read / add / modify / delete)
# ---------------------------------------------------------------------------

@app.get(
    "/api/tables",
    tags=["API"],
    summary="List available tables",
    response_model=List[str],
)
def list_tables():
    """Returns the whitelist of tables this API can read from and write to."""
    return TABLES


@app.get(
    "/api/table/{table_name}/meta",
    tags=["API"],
    summary="Get a table's columns and primary key (no rows)",
)
def get_table_meta(table_name: str):
    validate_table(table_name)
    return {"primary_key": table_primary_key(table_name)}


@app.get(
    "/api/table/{table_name}/schema",
    tags=["API"],
    summary="Get validation rules (type, pattern, required) for each column",
)
def get_table_schema_endpoint(table_name: str):
    validate_table(table_name)
    return {"columns": get_table_schema(table_name)}


@app.get(
    "/api/table/{table_name}",
    tags=["API"],
    summary="Get all rows from a table (JSON)",
    response_model=QueryResponse,
)
def get_table_json(table_name: str):
    validate_table(table_name)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table_name}")
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return {"columns": cols, "rows": rows}
    except mysql.connector.Error as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if conn is not None:
            conn.close()


@app.post(
    "/api/table/{table_name}",
    tags=["API"],
    summary="Add a new row to a table",
    response_model=StatusResponse,
)
def insert_row(table_name: str, payload: RowData = Body(...)):
    validate_table(table_name)
    data = payload.data
    if not data:
        raise HTTPException(status_code=400, detail="No column data provided.")

    errors = validate_row_against_schema(table_name, data)
    errors.update(validate_foreign_keys(table_name, data))
    if errors:
        detail = "; ".join(f"{col}: {msg}" for col, msg in errors.items())
        raise HTTPException(status_code=422, detail=detail)

    cols = ", ".join(data.keys())
    placeholders = ", ".join(["%s"] * len(data))
    values = list(data.values())

    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
        return {"status": "success", "row_id": str(cur.lastrowid)}
    except mysql.connector.Error as e:
        raise HTTPException(status_code=400, detail=friendly_db_error(e))
    finally:
        if conn is not None:
            conn.close()


@app.put(
    "/api/table/{table_name}/{id_column}/{row_id}",
    tags=["API"],
    summary="Modify an existing row",
    response_model=StatusResponse,
)
def update_row(table_name: str, id_column: str, row_id: str, payload: RowData = Body(...)):
    validate_table(table_name)
    data = payload.data
    if not data:
        raise HTTPException(status_code=400, detail="No column data provided.")

    errors = validate_row_against_schema(table_name, data)
    errors.update(validate_foreign_keys(table_name, data))
    if errors:
        detail = "; ".join(f"{col}: {msg}" for col, msg in errors.items())
        raise HTTPException(status_code=422, detail=detail)

    set_clause = ", ".join([f"{col}=%s" for col in data])
    values = list(data.values()) + [row_id]

    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {table_name} SET {set_clause} WHERE {id_column}=%s",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No row found where {id_column}={row_id} in '{table_name}'.",
            )
        return {"status": "updated", "row_id": row_id}
    except mysql.connector.Error as e:
        raise HTTPException(status_code=400, detail=friendly_db_error(e))
    finally:
        if conn is not None:
            conn.close()


@app.delete(
    "/api/table/{table_name}/{id_column}/{row_id}",
    tags=["API"],
    summary="Delete a row",
    response_model=StatusResponse,
)
def delete_row(table_name: str, id_column: str, row_id: str):
    validate_table(table_name)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table_name} WHERE {id_column}=%s", [row_id])
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No row found where {id_column}={row_id} in '{table_name}'.",
            )
        return {"status": "deleted", "row_id": row_id}
    except mysql.connector.Error as e:
        raise HTTPException(status_code=400, detail=friendly_db_error(e))
    finally:
        if conn is not None:
            conn.close()


@app.post(
    "/api/query",
    tags=["API"],
    summary="Run a raw SELECT query",
    response_model=QueryResponse,
)
def run_query(payload: QueryPayload):
    query = payload.query.strip()
    if not query.lower().startswith("select"):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT statements are allowed on this endpoint.",
        )

    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return {"columns": cols, "rows": rows}
    except mysql.connector.Error as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if conn is not None:
            conn.close()
