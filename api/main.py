"""
API Backend — Dashboard de Faturamento VTEX
FastAPI + NeonDB (PostgreSQL)
"""

import os
import time
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL   = os.getenv("DATABASE_URL")
SYNC_SECRET    = os.getenv("SYNC_SECRET_TOKEN", "change-me")

log = logging.getLogger("uvicorn")

app = FastAPI(title="Dashboard VTEX API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Cache simples em memória (55min) ──────────────────────────
_cache: dict = {}
CACHE_TTL = 55 * 60  # 55 minutos em segundos


def cache_get(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    return None


def cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}


# ── Conexão banco ─────────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


def verify_sync_token(x_sync_token: Optional[str] = Header(None)):
    if x_sync_token != SYNC_SECRET:
        raise HTTPException(status_code=401, detail="Token inválido")
    return True


# ── Health ────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Status da última sincronização ───────────────────────────
@app.get("/api/sync/status")
def sync_status(db=Depends(get_db)):
    with db.cursor() as cur:
        cur.execute("""
            SELECT execution_time, records_processed, status, type
            FROM sync_logs
            WHERE status = 'success'
            ORDER BY execution_time DESC
            LIMIT 1
        """)
        row = cur.fetchone()
    if not row:
        return {"last_sync": None, "records_processed": 0}
    return {
        "last_sync": row["execution_time"].isoformat() if row["execution_time"] else None,
        "records_processed": row["records_processed"],
        "status": row["status"],
        "type": row["type"],
    }


# ── Disparo de sincronização delta ────────────────────────────
@app.post("/api/sync/run")
def sync_run(authorized=Depends(verify_sync_token)):
    """Endpoint seguro para disparo da sincronização. Chamado pelo cron-job.org."""
    import subprocess
    import threading

    def run_delta():
        try:
            subprocess.run(["python", "etl/delta_sync.py"], check=True)
        except Exception as e:
            log.error(f"Erro na sync: {e}")

    t = threading.Thread(target=run_delta, daemon=True)
    t.start()
    return {"status": "started", "message": "Sincronização delta iniciada em background"}


# ── Opções de filtros para o dashboard ───────────────────────
@app.get("/api/dashboard/filters")
def get_filters(db=Depends(get_db)):
    cache_key = "filters"
    cached = cache_get(cache_key)
    if cached:
        return cached

    with db.cursor() as cur:
        # Canais
        cur.execute("SELECT DISTINCT channel_type FROM orders WHERE channel_type IS NOT NULL ORDER BY channel_type")
        channels = [r["channel_type"] for r in cur.fetchall()]

        # Marcas
        cur.execute("""
            SELECT DISTINCT brand_name FROM order_items
            WHERE brand_name IS NOT NULL AND brand_name != ''
            ORDER BY brand_name
        """)
        brands = [r["brand_name"] for r in cur.fetchall()]

        # Categorias (pega o nome da categoria mais específica)
        cur.execute("""
            SELECT DISTINCT elem->>'name' AS cat_name
            FROM order_items, jsonb_array_elements(categories_json) AS elem
            WHERE categories_json IS NOT NULL AND jsonb_typeof(categories_json) = 'array'
            ORDER BY cat_name
        """)
        categories = [r["cat_name"] for r in cur.fetchall() if r["cat_name"]]

        # UTM Sources
        cur.execute("""
            SELECT DISTINCT utm_source FROM order_marketing
            WHERE utm_source IS NOT NULL AND utm_source != ''
            ORDER BY utm_source
        """)
        utm_sources = [r["utm_source"] for r in cur.fetchall()]

        # UTM Campaigns
        cur.execute("""
            SELECT DISTINCT utm_campaign FROM order_marketing
            WHERE utm_campaign IS NOT NULL AND utm_campaign != ''
            ORDER BY utm_campaign
        """)
        utm_campaigns = [r["utm_campaign"] for r in cur.fetchall()]

        # UTM Mediums
        cur.execute("""
            SELECT DISTINCT utm_medium FROM order_marketing
            WHERE utm_medium IS NOT NULL AND utm_medium != ''
            ORDER BY utm_medium
        """)
        utm_mediums = [r["utm_medium"] for r in cur.fetchall()]

        # Status
        cur.execute("SELECT DISTINCT status, status_description FROM orders ORDER BY status")
        statuses = [{"value": r["status"], "label": r["status_description"]} for r in cur.fetchall()]

    result = {
        "channels": channels,
        "brands": brands,
        "categories": categories,
        "utm_sources": utm_sources,
        "utm_campaigns": utm_campaigns,
        "utm_mediums": utm_mediums,
        "statuses": statuses,
    }
    cache_set(cache_key, result)
    return result


# ── Faturamento hora a hora ───────────────────────────────────
@app.get("/api/dashboard/hourly-revenue")
def hourly_revenue(
    date_from: str = Query(..., description="Data inicial YYYY-MM-DD"),
    date_to: str = Query(..., description="Data final YYYY-MM-DD"),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    utm_source: Optional[str] = Query(None),
    utm_campaign: Optional[str] = Query(None),
    utm_medium: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Filtrar por status (ex: invoiced)"),
    db=Depends(get_db),
):
    # Cache key baseado nos parâmetros
    cache_key = f"hourly:{date_from}:{date_to}:{channel}:{brand}:{category}:{utm_source}:{utm_campaign}:{utm_medium}:{status}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conditions = ["o.creation_date >= %s::date", "o.creation_date < (%s::date + INTERVAL '1 day')"]
    params = [date_from, date_to]

    if channel:
        conditions.append("o.channel_type = %s")
        params.append(channel)
    if status:
        conditions.append("o.status = %s")
        params.append(status)
    if utm_source:
        conditions.append("m.utm_source = %s")
        params.append(utm_source)
    if utm_campaign:
        conditions.append("m.utm_campaign = %s")
        params.append(utm_campaign)
    if utm_medium:
        conditions.append("m.utm_medium = %s")
        params.append(utm_medium)

    # Se filtrar por marca ou categoria, precisamos de JOIN com items
    needs_item_join = bool(brand or category)
    item_conditions = []
    if brand:
        item_conditions.append("oi.brand_name = %s")
        params.append(brand)
    if category:
        item_conditions.append("oi.categories_json @> %s::jsonb")
        params.append(f'[{{"name": "{category}"}}]')

    item_join = ""
    if needs_item_join:
        item_join = "JOIN order_items oi ON oi.order_id = o.order_id"
        if item_conditions:
            conditions.extend(item_conditions)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            DATE_TRUNC('hour', o.creation_date AT TIME ZONE 'America/Sao_Paulo') AS hour,
            COUNT(DISTINCT o.order_id) AS total_orders,
            SUM(o.value) AS total_revenue,
            AVG(o.value)::INTEGER AS avg_ticket,
            SUM(o.total_discounts) AS total_discounts,
            SUM(o.total_shipping) AS total_shipping
        FROM orders o
        LEFT JOIN order_marketing m ON m.order_id = o.order_id
        {item_join}
        WHERE {where_clause}
        GROUP BY hour
        ORDER BY hour
    """

    with db.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    result = {
        "data": [
            {
                "hour": row["hour"].isoformat() if row["hour"] else None,
                "hour_label": row["hour"].strftime("%H:00") if row["hour"] else None,
                "total_orders": row["total_orders"],
                "total_revenue": row["total_revenue"] / 100 if row["total_revenue"] else 0,  # centavos → reais
                "avg_ticket": row["avg_ticket"] / 100 if row["avg_ticket"] else 0,
                "total_discounts": (row["total_discounts"] or 0) / 100,
                "total_shipping": (row["total_shipping"] or 0) / 100,
            }
            for row in rows
        ],
        "summary": {
            "total_revenue": sum(r["total_revenue"] / 100 for r in rows if r["total_revenue"]),
            "total_orders": sum(r["total_orders"] for r in rows),
            "avg_ticket": (
                sum(r["total_revenue"] or 0 for r in rows) /
                sum(r["total_orders"] for r in rows)
            ) / 100 if rows and sum(r["total_orders"] for r in rows) > 0 else 0,
        },
    }

    cache_set(cache_key, result)
    return result


# ── KPIs resumidos ────────────────────────────────────────────
@app.get("/api/dashboard/kpis")
def get_kpis(
    date_from: str = Query(...),
    date_to: str = Query(...),
    channel: Optional[str] = Query(None),
    db=Depends(get_db),
):
    conditions = ["creation_date >= %s::date", "creation_date < (%s::date + INTERVAL '1 day')"]
    params = [date_from, date_to]
    if channel:
        conditions.append("channel_type = %s")
        params.append(channel)

    where = " AND ".join(conditions)
    with db.cursor() as cur:
        cur.execute(f"""
            SELECT
                COUNT(*) AS total_orders,
                SUM(value) AS total_revenue,
                AVG(value)::INTEGER AS avg_ticket,
                SUM(CASE WHEN status IN ('invoiced','payment-approved') THEN value ELSE 0 END) AS approved_revenue,
                SUM(CASE WHEN status = 'canceled' THEN 1 ELSE 0 END) AS canceled_orders
            FROM orders
            WHERE {where}
        """, params)
        row = cur.fetchone()

    return {
        "total_orders": row["total_orders"] or 0,
        "total_revenue": (row["total_revenue"] or 0) / 100,
        "avg_ticket": (row["avg_ticket"] or 0) / 100,
        "approved_revenue": (row["approved_revenue"] or 0) / 100,
        "canceled_orders": row["canceled_orders"] or 0,
    }
