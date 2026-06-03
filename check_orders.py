import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

q = """
SELECT COALESCE(SUM(o.value), 0) FROM orders o 
WHERE (o.creation_date AT TIME ZONE 'America/Sao_Paulo')::date >= '2026-06-03'::date 
AND (o.creation_date AT TIME ZONE 'America/Sao_Paulo')::date <= '2026-06-03'::date
"""
cur.execute(q)
print(cur.fetchone())
