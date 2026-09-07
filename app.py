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

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>APC Database API</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    padding: 40px;
                }
                .container {
                    background: white;
                    width: 600px;
                    margin: auto;
                    padding: 25px;
                    border-radius: 10px;
                    box-shadow: 0px 0px 10px rgba(0,0,0,0.15);
                }
                h1 {
                    text-align: center;
                    color: #333;
                }
                ul {
                    list-style: none;
                    padding: 0;
                }
                li {
                    margin: 10px 0;
                }
                a {
                    text-decoration: none;
                    font-size: 18px;
                    color: #0066cc;
                }
                a:hover {
                    text-decoration: underline;
                }
                .footer {
                    margin-top: 25px;
                    text-align: center;
                }
            </style>
        </head>

        <body>
            <div class="container">
                <h1>APC Database API</h1>
                <p style="text-align:center;">Select a table to display:</p>

                <ul>
                    <li><a href="/table/patient">Patient Table</a></li>
                    <li><a href="/table/physician">Physician Table</a></li>
                    <li><a href="/table/consultation">Consultation Table</a></li>
                    <li><a href="/table/hospital">Hospital Table</a></li>
                    <li><a href="/table/hospital_location">Hospital Location Table</a></li>
                    <li><a href="/table/diagnosis">Diagnosis Table</a></li>
                    <li><a href="/table/coveragepolicy">Coverage Policy Table</a></li>
                    <li><a href="/table/speciality">Speciality</a></li>
                    <li><a href="/table/physician_speciality">Physician Speciality Table</a></li>
                </ul>

                <div class="footer">
                    <p>View API documentation:</p>
                    <a href="/docs">Swagger UI</a>
                </div>
            </div>
        </body>
    </html>
    """



from fastapi.responses import HTMLResponse

@app.get("/table/{table_name}", response_class=HTMLResponse)
def get_table(table_name: str):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table_name}")
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        conn.close()

        table_html = "<table><tr>"
        for col in cols:
            table_html += f"<th>{col}</th>"
        table_html += "</tr>"

        for row in rows:
            table_html += "<tr>"
            for cell in row:
                table_html += f"<td>{cell}</td>"
            table_html += "</tr>"

        table_html += "</table>"

        return f"""
        <html>
            <head>
                <title>{table_name.title()} Table</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        background-color: #f4f4f4;
                        padding: 40px;
                    }}
                    .container {{
                        background: white;
                        width: 900px;
                        margin: auto;
                        padding: 25px;
                        border-radius: 10px;
                        box-shadow: 0px 0px 10px rgba(0,0,0,0.15);
                    }}
                    h1 {{
                        text-align: center;
                        color: #333;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 20px;
                    }}
                    th, td {{
                        padding: 10px;
                        border: 1px solid #ccc;
                        text-align: left;
                    }}
                    th {{
                        background-color: #e3e3e3;
                    }}
                    a {{
                        color: #0066cc;
                        text-decoration: none;
                        font-size: 18px;
                    }}
                    a:hover {{
                        text-decoration: underline;
                    }}
                    .back {{
                        margin-top: 20px;
                        text-align: center;
                    }}
                </style>
            </head>

            <body>
                <div class="container">
                    <h1>{table_name.replace("_", " ").title()} Table</h1>
                    {table_html}

                    <div class="back">
                        <a href="/">⬅ Back to Menu</a>
                    </div>
                </div>
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
