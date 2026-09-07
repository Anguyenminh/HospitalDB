# Bryan Pham | Austin Nguyenminh 
# #1002120409| #1002097413

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import mysql.connector


app = FastAPI()


def get_conn():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="apc_db"
    )

# Tables exposed in the sidebar index, in the order they're listed.
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

# Shared visual language for both pages: a quiet records-ledger look
# (slate ink, one clinical-green accent, monospace for tabular data)
# rather than a generic centered card.
BASE_STYLE = """
    :root {
        --ink: #1C2733;
        --paper: #FAFAF8;
        --panel: #FFFFFF;
        --line: #E1DED6;
        --muted: #6B7280;
        --accent: #3E6D5C;
        --accent-soft: #E9EFEC;
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
        max-width: 1100px;
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
"""


@app.get("/", response_class=HTMLResponse)
def home():
    nav_items = "".join(
        f'<li><a href="/table/{t}">{t.replace("_", " ").title()}</a></li>'
        for t in TABLES
    )
    return f"""
    <html>
        <head>
            <title>APC Records</title>
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
            <style>{BASE_STYLE}</style>
        </head>
        <body>
            <aside class="sidebar">
                <p class="brand">APC Records</p>
                <h2>Table Index</h2>
                <nav><ul>{nav_items}</ul></nav>
                <a class="docs-link" href="/docs">API documentation &rarr;</a>
            </aside>
            <main>
                <h1>Ambulatory Patient Care</h1>
                <p class="lede">Select a table from the index to view its records.</p>
            </main>
        </body>
    </html>
    """


@app.get("/table/{table_name}", response_class=HTMLResponse)
def get_table(table_name: str):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table_name}")
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        conn.close()

        header_html = "".join(f"<th>{col}</th>" for col in cols)
        body_html = "".join(
            "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
            for row in rows
        )

        nav_items = "".join(
            f'<li><a class="{"active" if t == table_name else ""}" '
            f'href="/table/{t}">{t.replace("_", " ").title()}</a></li>'
            for t in TABLES
        )

        return f"""
        <html>
            <head>
                <title>{table_name.title()} — APC Records</title>
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
                <style>
                    {BASE_STYLE}
                    .meta {{
                        font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
                        font-size: 12px;
                        color: var(--muted);
                        margin: 0 0 24px;
                    }}
                    .table-wrap {{
                        border: 1px solid var(--line);
                        border-radius: 6px;
                        overflow: auto;
                        background: var(--panel);
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
                        font-size: 13px;
                    }}
                    th, td {{
                        padding: 10px 16px;
                        border-bottom: 1px solid var(--line);
                        text-align: left;
                        white-space: nowrap;
                    }}
                    thead th {{
                        background: var(--accent-soft);
                        color: var(--accent);
                        font-weight: 500;
                        border-bottom: 1px solid var(--line);
                        position: sticky;
                        top: 0;
                    }}
                    tbody tr:last-child td {{ border-bottom: none; }}
                    tbody tr:hover {{ background: var(--accent-soft); }}
                </style>
            </head>
            <body>
                <aside class="sidebar">
                    <p class="brand">APC Records</p>
                    <h2>Table Index</h2>
                    <nav><ul>{nav_items}</ul></nav>
                    <a class="docs-link" href="/docs">API documentation &rarr;</a>
                </aside>
                <main>
                    <h1>{table_name.replace("_", " ").title()}</h1>
                    <p class="meta">{len(rows)} row{"s" if len(rows) != 1 else ""} &middot; {len(cols)} columns</p>
                    <div class="table-wrap">
                        <table>
                            <thead><tr>{header_html}</tr></thead>
                            <tbody>{body_html}</tbody>
                        </table>
                    </div>
                </main>
            </body>
        </html>
        """

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/insert/{table_name}")
def insert_row(table_name: str, data: dict):
    try:
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        values = list(data.values())

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})",
            values
        )
        conn.commit()
        conn.close()
        return {"status": "success"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/update/{table_name}/{id_column}/{row_id}")
def update_row(table_name: str, id_column: str, row_id: str, data: dict):
    try:
        set_clause = ", ".join([f"{col}=%s" for col in data])
        values = list(data.values()) + [row_id]

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {table_name} SET {set_clause} WHERE {id_column}=%s",
            values
        )
        conn.commit()
        conn.close()
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/query")
def run_query(payload: dict):
    query = payload.get("query")
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        conn.close()
        return {"columns": cols, "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))