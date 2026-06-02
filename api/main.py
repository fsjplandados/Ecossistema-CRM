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

        # UTMI Parts
        cur.execute("""
            SELECT DISTINCT utmi_part FROM order_marketing
            WHERE utmi_part IS NOT NULL AND utmi_part != ''
            ORDER BY utmi_part
        """)
        utmi_parts = [r["utmi_part"] for r in cur.fetchall()]

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
        "utmi_parts": utmi_parts,
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
    utmi_part: Optional[str] = Query(None),
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
    utmi_part_v = parse_multi(utmi_part)
    status_v = parse_multi(status)

    cache_key = f"hourly:{date_from}:{date_to}:{channel}:{brand}:{category}:{utm_source}:{utm_campaign}:{utm_medium}:{utmi_part}:{status}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Condicoes de data com timezone correto (America/Sao_Paulo)
    conditions = [f"{TZ_DATE} >= %s::date", f"{TZ_DATE} <= %s::date"]
    params: list = [date_from, date_to]

    add_in_condition(conditions, params, "o.channel_type", channel_v)
    add_in_condition(conditions, params, "o.status", status_v)

    # UTM — requer JOIN com marketing
    needs_mkt = bool(utm_source_v or utm_campaign_v or utm_medium_v or utmi_part_v)
    add_in_condition(conditions, params, "m.utm_source", utm_source_v)
    add_in_condition(conditions, params, "m.utm_campaign", utm_campaign_v)
    add_in_condition(conditions, params, "m.utm_medium", utm_medium_v)
    add_in_condition(conditions, params, "m.utmi_part", utmi_part_v)

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
    utm_campaign: Optional[str] = Query(None),
    utm_medium: Optional[str] = Query(None),
    utmi_part: Optional[str] = Query(None),
    db=Depends(get_db),
):
    channel_v = parse_multi(channel)
    brand_v = parse_multi(brand)
    category_v = parse_multi(category)
    utm_source_v = parse_multi(utm_source)
    utm_campaign_v = parse_multi(utm_campaign)
    utm_medium_v = parse_multi(utm_medium)
    utmi_part_v = parse_multi(utmi_part)

    cache_key = f"kpis:{date_from}:{date_to}:{channel}:{brand}:{category}:{utm_source}:{utm_campaign}:{utm_medium}:{utmi_part}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Condicoes de filtro (nao-data)
    filter_conds: list = []
    filter_params: list = []
    add_in_condition(filter_conds, filter_params, "o.channel_type", channel_v)

    mkt_join = ""
    if utm_source_v or utm_campaign_v or utm_medium_v or utmi_part_v:
        mkt_join = "LEFT JOIN order_marketing m ON m.order_id = o.order_id"
        add_in_condition(filter_conds, filter_params, "m.utm_source", utm_source_v)
        add_in_condition(filter_conds, filter_params, "m.utm_campaign", utm_campaign_v)
        add_in_condition(filter_conds, filter_params, "m.utm_medium", utm_medium_v)
        add_in_condition(filter_conds, filter_params, "m.utmi_part", utmi_part_v)

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


# ── Performance por Categoria ─────────────────────────────────
@app.get("/api/dashboard/categories-performance")
def get_categories_performance(
    date_from: str = Query(...),
    date_to: str = Query(...),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    utm_source: Optional[str] = Query(None),
    utm_campaign: Optional[str] = Query(None),
    utm_medium: Optional[str] = Query(None),
    utmi_part: Optional[str] = Query(None),
    db=Depends(get_db),
):
    channel_v = parse_multi(channel)
    brand_v = parse_multi(brand)
    category_v = parse_multi(category)
    utm_source_v = parse_multi(utm_source)
    utm_campaign_v = parse_multi(utm_campaign)
    utm_medium_v = parse_multi(utm_medium)
    utmi_part_v = parse_multi(utmi_part)

    cache_key = f"cat_perf:{date_from}:{date_to}:{channel}:{brand}:{category}:{utm_source}:{utm_campaign}:{utm_medium}:{utmi_part}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    filter_conds = []
    filter_params = []
    add_in_condition(filter_conds, filter_params, "o.channel_type", channel_v)

    mkt_join = ""
    if utm_source_v or utm_campaign_v or utm_medium_v or utmi_part_v:
        mkt_join = "LEFT JOIN order_marketing m ON m.order_id = o.order_id"
        add_in_condition(filter_conds, filter_params, "m.utm_source", utm_source_v)
        add_in_condition(filter_conds, filter_params, "m.utm_campaign", utm_campaign_v)
        add_in_condition(filter_conds, filter_params, "m.utm_medium", utm_medium_v)
        add_in_condition(filter_conds, filter_params, "m.utmi_part", utmi_part_v)

    if brand_v:
        ph = ",".join(["%s"] * len(brand_v))
        filter_conds.append(f"oi.brand_name IN ({ph})")
        filter_params.extend(brand_v)

    if category_v:
        cat_parts = []
        for cat in category_v:
            cat_parts.append("(oi.categories_json->-1)->>'name' = %s")
            filter_params.append(cat)
        filter_conds.append(f"({' OR '.join(cat_parts)})" if len(cat_parts) > 1 else cat_parts[0])

    extra_where = (" AND " + " AND ".join(filter_conds)) if filter_conds else ""

    def run_cat_query(cur, df, dt):
        p = [df, dt] + list(filter_params)
        q = f"""
            SELECT 
                (oi.categories_json->-1)->>'name' AS cat_name,
                SUM(oi.selling_price * oi.quantity) AS revenue,
                SUM(oi.quantity) AS qty_sold,
                COUNT(DISTINCT o.order_id) AS total_orders
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id
            {mkt_join}
            WHERE {TZ_DATE} >= %s::date AND {TZ_DATE} <= %s::date
              AND (oi.categories_json->-1)->>'name' IS NOT NULL
              {extra_where}
            GROUP BY cat_name
        """
        cur.execute(q, p)
        return {row["cat_name"]: row for row in cur.fetchall() if row["cat_name"]}

    with db.cursor() as cur:
        curr_data = run_cat_query(cur, date_from, date_to)

        # Yesterday
        df_obj = date_cls.fromisoformat(date_from)
        yd_str = (df_obj - timedelta(days=1)).isoformat()
        yd_data = run_cat_query(cur, yd_str, yd_str)

        # 7d Avg
        a7_start = (df_obj - timedelta(days=7)).isoformat()
        a7_end = (df_obj - timedelta(days=1)).isoformat()
        a7_data = run_cat_query(cur, a7_start, a7_end)

        # Previous Month (same day approx)
        try:
            prev_mo_str = df_obj.replace(month=df_obj.month - 1).isoformat()
        except ValueError:
            prev_mo_str = (df_obj - timedelta(days=30)).isoformat()
        pm_data = run_cat_query(cur, prev_mo_str, prev_mo_str)

    results = []
    for cat_name, row in curr_data.items():
        rev = row["revenue"] or 0
        qty = row["qty_sold"] or 0
        orders = row["total_orders"] or 0

        # YD
        yd_row = yd_data.get(cat_name, {})
        y_rev = yd_row.get("revenue") or 0
        y_qty = yd_row.get("qty_sold") or 0
        y_orders = yd_row.get("total_orders") or 0

        # 7D
        a7_row = a7_data.get(cat_name, {})
        a7_rev = (a7_row.get("revenue") or 0) / 7
        a7_qty = (a7_row.get("qty_sold") or 0) / 7
        a7_orders = (a7_row.get("total_orders") or 0) / 7

        # PM
        pm_row = pm_data.get(cat_name, {})
        pm_rev = pm_row.get("revenue") or 0
        pm_qty = pm_row.get("qty_sold") or 0
        pm_orders = pm_row.get("total_orders") or 0

        results.append({
            "category": cat_name,
            "revenue": rev / 100,
            "qty_sold": qty,
            "total_orders": orders,
            "avg_ticket": (rev / orders / 100) if orders > 0 else 0,
            "items_per_order": (qty / orders) if orders > 0 else 0,
            "avg_price": (rev / qty / 100) if qty > 0 else 0,
            
            "yd_revenue": y_rev / 100,
            "yd_qty": y_qty,
            "yd_orders": y_orders,
            "yd_avg_ticket": (y_rev / y_orders / 100) if y_orders > 0 else 0,
            "yd_items_per_order": (y_qty / y_orders) if y_orders > 0 else 0,
            "yd_avg_price": (y_rev / y_qty / 100) if y_qty > 0 else 0,

            "a7_revenue": a7_rev / 100,
            "a7_qty": a7_qty,
            "a7_orders": a7_orders,
            "a7_avg_ticket": (a7_rev / a7_orders / 100) if a7_orders > 0 else 0,
            "a7_items_per_order": (a7_qty / a7_orders) if a7_orders > 0 else 0,
            "a7_avg_price": (a7_rev / a7_qty / 100) if a7_qty > 0 else 0,

            "pm_revenue": pm_rev / 100,
            "pm_qty": pm_qty,
            "pm_orders": pm_orders,
            "pm_avg_ticket": (pm_rev / pm_orders / 100) if pm_orders > 0 else 0,
            "pm_items_per_order": (pm_qty / pm_orders) if pm_orders > 0 else 0,
            "pm_avg_price": (pm_rev / pm_qty / 100) if pm_qty > 0 else 0,
        })

    # Sort default by revenue desc
    results.sort(key=lambda x: x["revenue"], reverse=True)

    cache_set(cache_key, results, get_cache_ttl(date_from))
    return results


# ── Produtos Mais Vendidos ────────────────────────────────────
@app.get("/api/dashboard/top-products")
def get_top_products(
    date_from: str = Query(...),
    date_to: str = Query(...),
    hour: Optional[str] = Query(None, description="Filtrar por hora especifica HH:00"),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    utm_source: Optional[str] = Query(None),
    utm_campaign: Optional[str] = Query(None),
    utm_medium: Optional[str] = Query(None),
    utmi_part: Optional[str] = Query(None),
    db=Depends(get_db),
):
    channel_v = parse_multi(channel)
    brand_v = parse_multi(brand)
    category_v = parse_multi(category)
    utm_source_v = parse_multi(utm_source)
    utm_campaign_v = parse_multi(utm_campaign)
    utm_medium_v = parse_multi(utm_medium)
    utmi_part_v = parse_multi(utmi_part)

    cache_key = f"top_prod:{date_from}:{date_to}:{hour}:{channel}:{brand}:{category}:{utm_source}:{utm_campaign}:{utm_medium}:{utmi_part}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    filter_conds = []
    filter_params = []
    
    # Base date filter
    filter_conds.append(f"{TZ_DATE} >= %s::date AND {TZ_DATE} <= %s::date")
    filter_params.extend([date_from, date_to])

    if hour:
        # hour ex: "14:00" -> extract "14"
        hr = hour.split(":")[0]
        filter_conds.append(f"EXTRACT(HOUR FROM o.creation_date AT TIME ZONE '{TZ}') = %s")
        filter_params.append(hr)

    add_in_condition(filter_conds, filter_params, "o.channel_type", channel_v)

    mkt_join = ""
    if utm_source_v or utm_campaign_v or utm_medium_v or utmi_part_v:
        mkt_join = "LEFT JOIN order_marketing m ON m.order_id = o.order_id"
        add_in_condition(filter_conds, filter_params, "m.utm_source", utm_source_v)
        add_in_condition(filter_conds, filter_params, "m.utm_campaign", utm_campaign_v)
        add_in_condition(filter_conds, filter_params, "m.utm_medium", utm_medium_v)
        add_in_condition(filter_conds, filter_params, "m.utmi_part", utmi_part_v)

    if brand_v:
        ph = ",".join(["%s"] * len(brand_v))
        filter_conds.append(f"oi.brand_name IN ({ph})")
        filter_params.extend(brand_v)

    if category_v:
        cat_parts = []
        for cat in category_v:
            cat_parts.append("(oi.categories_json->-1)->>'name' = %s")
            filter_params.append(cat)
        filter_conds.append(f"({' OR '.join(cat_parts)})" if len(cat_parts) > 1 else cat_parts[0])

    where_clause = " AND ".join(filter_conds)

    q = f"""
        SELECT 
            oi.product_id,
            oi.name,
            MAX(oi.image_url) AS image_url,
            SUM(oi.selling_price * oi.quantity) AS revenue,
            SUM(oi.quantity) AS qty_sold
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        {mkt_join}
        WHERE {where_clause}
        GROUP BY oi.product_id, oi.name
        ORDER BY revenue DESC
        LIMIT 50
    """

    with db.cursor() as cur:
        cur.execute(q, filter_params)
        curr_rows = cur.fetchall()
        
        # Calculate overall total revenue for % calc
        cur.execute(f"SELECT SUM(oi.selling_price * oi.quantity) as total FROM order_items oi JOIN orders o ON o.order_id = oi.order_id {mkt_join} WHERE {where_clause}", filter_params)
        total_rev = (cur.fetchone()["total"] or 0) / 100

        # Yesterday comparison for the arrow indicators
        df_obj = date_cls.fromisoformat(date_from)
        yd_str = (df_obj - timedelta(days=1)).isoformat()
        
        yd_params = list(filter_params)
        # replace date_from and date_to with yesterday
        yd_params[0] = yd_str
        yd_params[1] = yd_str
        
        y_q = f"""
            SELECT oi.product_id, SUM(oi.selling_price * oi.quantity) AS revenue
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id
            {mkt_join}
            WHERE {where_clause}
            GROUP BY oi.product_id
        """
        cur.execute(y_q, yd_params)
        yd_rows = {row["product_id"]: row["revenue"] for row in cur.fetchall()}

    results = []
    for row in curr_rows:
        rev = (row["revenue"] or 0) / 100
        y_rev = (yd_rows.get(row["product_id"]) or 0) / 100
        
        results.append({
            "product_id": row["product_id"],
            "name": row["name"],
            "image_url": row["image_url"],
            "revenue": rev,
            "qty_sold": row["qty_sold"] or 0,
            "participation_pct": (rev / total_rev * 100) if total_rev > 0 else 0,
            "revenue_yesterday": y_rev
        })

    cache_set(cache_key, results, get_cache_ttl(date_from))
    return results


# ── Performance por Produto (Drill-Down) ──────────────────────
@app.get("/api/dashboard/products-performance")
def get_products_performance(
    date_from: str = Query(...),
    date_to: str = Query(...),
    channel: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    utm_source: Optional[str] = Query(None),
    utm_campaign: Optional[str] = Query(None),
    utm_medium: Optional[str] = Query(None),
    utmi_part: Optional[str] = Query(None),
    db=Depends(get_db),
):
    channel_v = parse_multi(channel)
    brand_v = parse_multi(brand)
    category_v = parse_multi(category)
    utm_source_v = parse_multi(utm_source)
    utm_campaign_v = parse_multi(utm_campaign)
    utm_medium_v = parse_multi(utm_medium)
    utmi_part_v = parse_multi(utmi_part)

    cache_key = f"prod_perf:{date_from}:{date_to}:{channel}:{brand}:{category}:{utm_source}:{utm_campaign}:{utm_medium}:{utmi_part}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    filter_conds = []
    filter_params = []
    add_in_condition(filter_conds, filter_params, "o.channel_type", channel_v)

    mkt_join = ""
    if utm_source_v or utm_campaign_v or utm_medium_v or utmi_part_v:
        mkt_join = "LEFT JOIN order_marketing m ON m.order_id = o.order_id"
        add_in_condition(filter_conds, filter_params, "m.utm_source", utm_source_v)
        add_in_condition(filter_conds, filter_params, "m.utm_campaign", utm_campaign_v)
        add_in_condition(filter_conds, filter_params, "m.utm_medium", utm_medium_v)
        add_in_condition(filter_conds, filter_params, "m.utmi_part", utmi_part_v)

    if brand_v:
        ph = ",".join(["%s"] * len(brand_v))
        filter_conds.append(f"oi.brand_name IN ({ph})")
        filter_params.extend(brand_v)

    if category_v:
        cat_parts = []
        for cat in category_v:
            cat_parts.append("(oi.categories_json->-1)->>'name' = %s")
            filter_params.append(cat)
        filter_conds.append(f"({' OR '.join(cat_parts)})" if len(cat_parts) > 1 else cat_parts[0])

    extra_where = (" AND " + " AND ".join(filter_conds)) if filter_conds else ""

    def run_prod_query(cur, df, dt):
        p = [df, dt] + list(filter_params)
        q = f"""
            SELECT 
                oi.name AS item_name,
                SUM(oi.selling_price * oi.quantity) AS revenue,
                SUM(oi.quantity) AS qty_sold,
                COUNT(DISTINCT o.order_id) AS total_orders
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id
            {mkt_join}
            WHERE {TZ_DATE} >= %s::date AND {TZ_DATE} <= %s::date
              AND oi.name IS NOT NULL
              {extra_where}
            GROUP BY oi.name
        """
        cur.execute(q, p)
        return {row["item_name"]: row for row in cur.fetchall() if row["item_name"]}

    with db.cursor() as cur:
        curr_data = run_prod_query(cur, date_from, date_to)

        df_obj = date_cls.fromisoformat(date_from)
        yd_str = (df_obj - timedelta(days=1)).isoformat()
        yd_data = run_prod_query(cur, yd_str, yd_str)

        a7_start = (df_obj - timedelta(days=7)).isoformat()
        a7_end = (df_obj - timedelta(days=1)).isoformat()
        a7_data = run_prod_query(cur, a7_start, a7_end)

        try:
            prev_mo_str = df_obj.replace(month=df_obj.month - 1).isoformat()
        except ValueError:
            prev_mo_str = (df_obj - timedelta(days=30)).isoformat()
        pm_data = run_prod_query(cur, prev_mo_str, prev_mo_str)

    results = []
    for item_name, row in curr_data.items():
        rev = row["revenue"] or 0
        qty = row["qty_sold"] or 0
        orders = row["total_orders"] or 0

        yd_row = yd_data.get(item_name, {})
        y_rev = yd_row.get("revenue") or 0
        y_qty = yd_row.get("qty_sold") or 0
        y_orders = yd_row.get("total_orders") or 0

        a7_row = a7_data.get(item_name, {})
        a7_rev = (a7_row.get("revenue") or 0) / 7
        a7_qty = (a7_row.get("qty_sold") or 0) / 7
        a7_orders = (a7_row.get("total_orders") or 0) / 7

        pm_row = pm_data.get(item_name, {})
        pm_rev = pm_row.get("revenue") or 0
        pm_qty = pm_row.get("qty_sold") or 0
        pm_orders = pm_row.get("total_orders") or 0

        results.append({
            "category": item_name,
            "revenue": rev / 100,
            "qty_sold": qty,
            "total_orders": orders,
            "avg_ticket": (rev / orders / 100) if orders > 0 else 0,
            "items_per_order": (qty / orders) if orders > 0 else 0,
            "avg_price": (rev / qty / 100) if qty > 0 else 0,
            
            "yd_revenue": y_rev / 100,
            "yd_qty": y_qty,
            "yd_orders": y_orders,
            "yd_avg_ticket": (y_rev / y_orders / 100) if y_orders > 0 else 0,
            "yd_items_per_order": (y_qty / y_orders) if y_orders > 0 else 0,
            "yd_avg_price": (y_rev / y_qty / 100) if y_qty > 0 else 0,

            "a7_revenue": a7_rev / 100,
            "a7_qty": a7_qty,
            "a7_orders": a7_orders,
            "a7_avg_ticket": (a7_rev / a7_orders / 100) if a7_orders > 0 else 0,
            "a7_items_per_order": (a7_qty / a7_orders) if a7_orders > 0 else 0,
            "a7_avg_price": (a7_rev / a7_qty / 100) if a7_qty > 0 else 0,

            "pm_revenue": pm_rev / 100,
            "pm_qty": pm_qty,
            "pm_orders": pm_orders,
            "pm_avg_ticket": (pm_rev / pm_orders / 100) if pm_orders > 0 else 0,
            "pm_items_per_order": (pm_qty / pm_orders) if pm_orders > 0 else 0,
            "pm_avg_price": (pm_rev / pm_qty / 100) if pm_qty > 0 else 0,
        })

    results.sort(key=lambda x: x["revenue"], reverse=True)
    cache_set(cache_key, results, get_cache_ttl(date_from))
    return results
