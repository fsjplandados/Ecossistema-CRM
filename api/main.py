"""
API Backend — Dashboard de Faturamento VTEX
FastAPI + NeonDB (PostgreSQL)
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta, date as date_cls
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

app = FastAPI(title="Dashboard VTEX API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Cache simples em memória ──────────────────────────────────
_cache: dict = {}
CACHE_TTL = 55 * 60       # 55 minutos para dados históricos
CACHE_TTL_TODAY = 3 * 60   # 3 minutos para dados de hoje


def cache_get(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < entry.get("ttl", CACHE_TTL):
        return entry["data"]
    return None


def cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "ts": time.time(), "ttl": ttl}


def cache_clear():
    """Limpa todo o cache em memória."""
    _cache.clear()


# ── Conexão banco ─────────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


def verify_sync_token(x_sync_token: Optional[str] = Header(None)):
    if x_sync_token != SYNC_SECRET:
        raise HTTPException(status_code=401, detail="Token invalido")
    return True


# ── Helpers para multi-filtros ────────────────────────────────
def parse_multi(value: Optional[str]) -> Optional[list]:
    """Converte valor separado por virgula em lista."""
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items if items else None


def add_in_condition(conditions: list, params: list, column: str, values: Optional[list]):
    """Adiciona condicao IN para multi-filtros."""
    if values:
        ph = ",".join(["%s"] * len(values))
        conditions.append(f"{column} IN ({ph})")
        params.extend(values)


def build_item_subquery(brand_values: Optional[list], category_values: Optional[list]):
    """Subquery para filtrar por marca/categoria sem duplicar pedidos."""
    if not brand_values and not category_values:
        return "", []
    sub_conds = []
    sub_params = []
    if brand_values:
        ph = ",".join(["%s"] * len(brand_values))
        sub_conds.append(f"oi.brand_name IN ({ph})")
        sub_params.extend(brand_values)
    if category_values:
        cat_parts = []
        for cat in category_values:
            cat_parts.append("(oi.categories_json->-1)->>'name' = %s")
            sub_params.append(cat)
        sub_conds.append(f"({' OR '.join(cat_parts)})" if len(cat_parts) > 1 else cat_parts[0])
    where = " AND ".join(sub_conds)
    return f"o.order_id IN (SELECT DISTINCT oi.order_id FROM order_items oi WHERE {where})", sub_params


def get_cache_ttl(date_from: str) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return CACHE_TTL_TODAY if date_from == today else CACHE_TTL


# ── Timezone ──────────────────────────────────────────────────
TZ = "America/Sao_Paulo"
TZ_DATE = f"(o.creation_date AT TIME ZONE '{TZ}')::date"


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
            FROM sync_logs WHERE status = 'success'
            ORDER BY execution_time DESC LIMIT 1
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
    """Endpoint seguro para disparo da sincronizacao."""
    import subprocess
    import threading

    def run_delta():
        try:
            subprocess.run(["python", "etl/delta_sync.py"], check=True)
            cache_clear()
        except Exception as e:
            log.error(f"Erro na sync: {e}")

    t = threading.Thread(target=run_delta, daemon=True)
    t.start()
    return {"status": "started", "message": "Sincronizacao delta iniciada em background"}


# ── Filtros disponíveis ───────────────────────────────────────
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

        # Categorias raiz (departamento principal — ultimo elemento do array)
        cur.execute("""
            SELECT DISTINCT (categories_json->-1)->>'name' AS cat_name
            FROM order_items
            WHERE categories_json IS NOT NULL
              AND jsonb_typeof(categories_json) = 'array'
              AND jsonb_array_length(categories_json) > 0
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
    status: Optional[str] = Query(None),
    db=Depends(get_db),
):
    # Parse multi-filtros (aceita valores separados por virgula)
    channel_v = parse_multi(channel)
    brand_v = parse_multi(brand)
    category_v = parse_multi(category)
    utm_source_v = parse_multi(utm_source)
    utm_campaign_v = parse_multi(utm_campaign)
    utm_medium_v = parse_multi(utm_medium)
    status_v = parse_multi(status)

    cache_key = f"hourly:{date_from}:{date_to}:{channel}:{brand}:{category}:{utm_source}:{utm_campaign}:{utm_medium}:{status}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Condicoes de data com timezone correto (America/Sao_Paulo)
    conditions = [f"{TZ_DATE} >= %s::date", f"{TZ_DATE} <= %s::date"]
    params: list = [date_from, date_to]

    add_in_condition(conditions, params, "o.channel_type", channel_v)
    add_in_condition(conditions, params, "o.status", status_v)

    # UTM — requer JOIN com marketing
    needs_mkt = bool(utm_source_v or utm_campaign_v or utm_medium_v)
    add_in_condition(conditions, params, "m.utm_source", utm_source_v)
    add_in_condition(conditions, params, "m.utm_campaign", utm_campaign_v)
    add_in_condition(conditions, params, "m.utm_medium", utm_medium_v)

    # Marca/Categoria — subquery para evitar duplicacao de pedidos
    item_sub, item_params = build_item_subquery(brand_v, category_v)
    if item_sub:
        conditions.append(item_sub)
        params.extend(item_params)

    mkt_join = "LEFT JOIN order_marketing m ON m.order_id = o.order_id" if needs_mkt else ""
    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            DATE_TRUNC('hour', o.creation_date AT TIME ZONE '{TZ}') AS hour,
            COUNT(DISTINCT o.order_id) AS total_orders,
            SUM(o.value) AS total_revenue,
            AVG(o.value)::INTEGER AS avg_ticket,
            SUM(o.total_discounts) AS total_discounts,
            SUM(o.total_shipping) AS total_shipping
        FROM orders o
        {mkt_join}
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
                "total_revenue": row["total_revenue"] / 100 if row["total_revenue"] else 0,
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

    cache_set(cache_key, result, get_cache_ttl(date_from))
    return result


# ── KPIs resumidos com comparações ────────────────────────────
@app.get("/api/dashboard/kpis")
def get_kpis(
    date_from: str = Query(...),
    date_to: str = Query(...),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    utm_source: Optional[str] = Query(None),
    db=Depends(get_db),
):
    channel_v = parse_multi(channel)
    brand_v = parse_multi(brand)
    category_v = parse_multi(category)
    utm_source_v = parse_multi(utm_source)

    cache_key = f"kpis:{date_from}:{date_to}:{channel}:{brand}:{category}:{utm_source}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Condicoes de filtro (nao-data)
    filter_conds: list = []
    filter_params: list = []
    add_in_condition(filter_conds, filter_params, "o.channel_type", channel_v)

    mkt_join = ""
    if utm_source_v:
        mkt_join = "LEFT JOIN order_marketing m ON m.order_id = o.order_id"
        add_in_condition(filter_conds, filter_params, "m.utm_source", utm_source_v)

    item_sub, item_p = build_item_subquery(brand_v, category_v)
    if item_sub:
        filter_conds.append(item_sub)
        filter_params.extend(item_p)

    extra_where = (" AND " + " AND ".join(filter_conds)) if filter_conds else ""

    def run_kpi(cur, df, dt):
        p = [df, dt] + list(filter_params)
        q = f"""
            SELECT
                COUNT(DISTINCT o.order_id) AS total_orders,
                COALESCE(SUM(o.value), 0) AS total_revenue,
                COALESCE(AVG(o.value)::INTEGER, 0) AS avg_ticket,
                COALESCE(SUM(CASE WHEN o.status IN ('invoiced','payment-approved','handling','ready-for-handling','window-to-cancel') THEN o.value ELSE 0 END), 0) AS approved_revenue,
                SUM(CASE WHEN o.status = 'canceled' THEN 1 ELSE 0 END) AS canceled_orders
            FROM orders o
            {mkt_join}
            WHERE {TZ_DATE} >= %s::date AND {TZ_DATE} <= %s::date{extra_where}
        """
        cur.execute(q, p)
        return cur.fetchone()

    with db.cursor() as cur:
        r = run_kpi(cur, date_from, date_to)

        df = date_cls.fromisoformat(date_from)
        yd_str = (df - timedelta(days=1)).isoformat()
        yd = run_kpi(cur, yd_str, yd_str)

        a7_start = (df - timedelta(days=7)).isoformat()
        a7_end = (df - timedelta(days=1)).isoformat()
        a7 = run_kpi(cur, a7_start, a7_end)

    result = {
        "total_orders": r["total_orders"] or 0,
        "total_revenue": (r["total_revenue"] or 0) / 100,
        "avg_ticket": (r["avg_ticket"] or 0) / 100,
        "approved_revenue": (r["approved_revenue"] or 0) / 100,
        "canceled_orders": r["canceled_orders"] or 0,
        "yesterday_revenue": (yd["total_revenue"] or 0) / 100,
        "yesterday_orders": yd["total_orders"] or 0,
        "yesterday_ticket": (yd["avg_ticket"] or 0) / 100,
        "avg7d_revenue": (a7["total_revenue"] or 0) / 100 / 7,
        "avg7d_orders": (a7["total_orders"] or 0) // 7,
        "avg7d_ticket": (a7["avg_ticket"] or 0) / 100,
    }

    cache_set(cache_key, result, get_cache_ttl(date_from))
    return result
