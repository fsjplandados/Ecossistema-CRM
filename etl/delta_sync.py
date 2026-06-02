"""
ETL — Sincronização Delta (Horária)
Busca apenas pedidos criados ou atualizados desde a última sincronização.
Deve ser disparado via cron-job.org a cada hora.
"""

import os
import time
import json
import logging
from datetime import datetime, timezone, timedelta

import psycopg2
import requests
from dotenv import load_dotenv

# Reutiliza funções do hist_load
from hist_load import (
    vtex_get, upsert_order, update_sync_log,
    get_conn, VTEX_BASE_URL, PAGE_SIZE, RATE_SLEEP
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("delta_sync.log")],
)
log = logging.getLogger(__name__)


def get_last_sync_date(conn) -> datetime:
    """Retorna a data da última sincronização bem-sucedida."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT last_order_date, execution_time
            FROM sync_logs
            WHERE status = 'success'
            ORDER BY execution_time DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
        # Se não houver sync anterior, pegar últimas 2 horas
        return datetime.now(timezone.utc) - timedelta(hours=2)


def list_orders_delta(since_dt: datetime) -> list[str]:
    """Lista pedidos criados ou atualizados desde since_dt."""
    order_ids = set()

    # Busca por lastInteraction (pedidos atualizados)
    page = 1
    while True:
        since_str = since_dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        params = {
            "f_lastInteractionIn": f"lastInteractionIn:[{since_str} TO {now_str}]",
            "per_page": PAGE_SIZE,
            "page": page,
        }
        data = vtex_get(f"{VTEX_BASE_URL}/api/oms/pvt/orders", params=params)
        if not data or not data.get("list"):
            break
        batch = [o["orderId"] for o in data["list"]]
        order_ids.update(batch)
        log.info(f"  Página {page} (lastInteraction): {len(batch)} pedidos")
        if len(batch) < PAGE_SIZE or page >= 30:
            break
        page += 1

    return list(order_ids)


def run_delta_sync():
    log.info("=" * 60)
    log.info("INICIANDO SINCRONIZAÇÃO DELTA")
    log.info("=" * 60)

    conn = get_conn()
    conn.autocommit = False

    try:
        since_dt = get_last_sync_date(conn)
        log.info(f"Sincronizando desde: {since_dt}")

        order_ids = list_orders_delta(since_dt)
        log.info(f"Total de pedidos para processar: {len(order_ids)}")

        processed = 0
        errors = 0
        for order_id in order_ids:
            from hist_load import fetch_order
            order = fetch_order(order_id)
            if not order:
                errors += 1
                continue
            try:
                upsert_order(conn, order)
                conn.commit()
                processed += 1
            except Exception as e:
                conn.rollback()
                log.error(f"Erro no pedido {order_id}: {e}")
                errors += 1

        # Registrar sincronização
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sync_logs (type, status, records_processed, last_order_date)
                VALUES ('delta', 'success', %s, NOW())
            """, (processed,))
        conn.commit()

        log.info(f"✅ Delta concluído — {processed} processados, {errors} erros")
        return {"status": "success", "processed": processed, "errors": errors}

    except Exception as e:
        update_sync_log(conn, "delta", "error", 0, str(e))
        log.error(f"Falha na sincronização: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_delta_sync()
