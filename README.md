# HospitalDB
A FastAPI + MySQL web app for browsing and managing a hospital/patient care database
File Descriptions:

app.py: 
is the file that provides the HTML interface for viewing the tables. 

Features:
- Home page with links to each database table
- endpoint displays any table in an HTML format
- offers basic navigation for readability
- Uses MySQL queries to fetch the rows and columns


gui.py:
Provides API routes that let other programs read and update the database. 

Features:
- selecting tables
- inserting rows
- updating rows
- running custom queries

How to Run:

1. Install dependancies:
pip install fastapi uvicorn mysql-connector-python
2. Start Server:
uvicorn app:app --reload
3. open interface in browser.
http://127.0.0.1:8000/


