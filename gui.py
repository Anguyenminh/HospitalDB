# Bryan Pham | Austin Nguyenminh 
# #1002120409| #1002097413

from gui import FastAPI, HTTPException
import mysql.connector

def get_conn():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="YOUR_PASSWORD",
        database="apc_db"
    )


app = FastAPI()
DB_NAME = "apc_db"

@app.get("/table/{table_name}")
def get_table(table_name: str):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table_name}")
        rows = cur.fetchall()
        cols = [description[0] for description in cur.description]
        conn.close()
        return {"columns": cols, "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/insert/{table_name}")
def insert_row(table_name: str, data: dict):
    try:
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
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
def update_row(table_name: str, id_column: str, row_id: int, data: dict):
    try:
        set_clause = ", ".join([f"{col}=?" for col in data.keys()])
        values = list(data.values())
        values.append(row_id)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {table_name} SET {set_clause} WHERE {id_column}=?",
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
        cols = [d[0] for d in cur.description]
        conn.close()
        return {"columns": cols, "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
        
        
        