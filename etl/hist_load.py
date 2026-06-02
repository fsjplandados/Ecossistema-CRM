"""
ETL — Carga Histórica VTEX para NeonDB
Percorre todos os pedidos disponíveis na VTEX, mês a mês, e armazena TODOS
os dados no banco (incluindo raw_json para preservar tudo).
"""

import os
import time
import json
import logging
import psycopg2
import psycopg2.extras
import requests
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv()

# ── Configurações ────────────────────────────────────────────
VTEX_ACCOUNT    = os.getenv("VTEX_ACCOUNT_NAME", "sjdigital")
VTEX_ENV        = os.getenv("VTEX_ENVIRONMENT", "vtexcommercestable")
VTEX_APP_KEY    = os.getenv("VTEX_APP_KEY")
VTEX_APP_TOKEN  = os.getenv("VTEX_APP_TOKEN")
DATABASE_URL    = os.getenv("DATABASE_URL")
PAGE_SIZE       = int(os.getenv("VTEX_PAGE_SIZE", "100"))
RATE_SLEEP      = float(os.getenv("VTEX_RATE_LIMIT_SLEEP", "0.4"))
HIST_START      = os.getenv("HISTORICAL_START_DATE", "2023-01-01")

VTEX_BASE_URL   = f"https://{VTEX_ACCOUNT}.{VTEX_ENV}.com.br"
VTEX_HEADERS    = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-VTEX-API-AppKey": VTEX_APP_KEY,
    "X-VTEX-API-AppToken": VTEX_APP_TOKEN,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("hist_load.log")],
)
log = logging.getLogger(__name__)


# ── Conexão com banco ────────────────────────────────────────
def get_conn():
    return psycopg2.connect(DATABASE_URL)


# ── Funções VTEX ─────────────────────────────────────────────
def vtex_get(url: str, params: dict = None, retries: int = 5) -> dict | None:
    """GET na API VTEX com retry automático e rate limiting."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=VTEX_HEADERS, params=params, timeout=30)
            if resp.status_code == 200:
                time.sleep(RATE_SLEEP)
                return resp.json()
            elif resp.status_code == 429:
                wait = 10 * (attempt + 1)
                log.warning(f"Rate limit atingido. Aguardando {wait}s...")
                time.sleep(wait)
            elif resp.status_code in (500, 502, 503, 504):
                wait = 5 * (attempt + 1)
                log.warning(f"Erro {resp.status_code}. Tentativa {attempt+1}/{retries}. Aguardando {wait}s...")
                time.sleep(wait)
            else:
                log.error(f"Erro inesperado {resp.status_code}: {resp.text[:200]}")
                return None
        except requests.exceptions.Timeout:
            log.warning(f"Timeout. Tentativa {attempt+1}/{retries}")
            time.sleep(5)
        except Exception as e:
            log.error(f"Exceção: {e}")
            time.sleep(5)
    return None


def list_orders_by_window(start_dt: datetime, end_dt: datetime) -> list[str]:
    """Lista IDs de pedidos em uma janela de tempo."""
    order_ids = []
    page = 1
    while True:
        params = {
            "f_creationDate": f"creationDate:[{start_dt.strftime('%Y-%m-%dT%H:%M:%S')}Z TO {end_dt.strftime('%Y-%m-%dT%H:%M:%S')}Z]",
            "per_page": PAGE_SIZE,
            "page": page,
        }
        data = vtex_get(f"{VTEX_BASE_URL}/api/oms/pvt/orders", params=params)
        if not data or not data.get("list"):
            break
        batch = [o["orderId"] for o in data["list"]]
        order_ids.extend(batch)
        log.info(f"  Página {page}: {len(batch)} pedidos (total={len(order_ids)})")
        if len(batch) < PAGE_SIZE:
            break
        if page >= 30:  # VTEX limita a 30 páginas por filtro
            log.warning("Limite de 30 páginas atingido. Quebre a janela em períodos menores.")
            break
        page += 1
    return order_ids


def fetch_order(order_id: str) -> dict | None:
    """Busca o pedido completo na VTEX."""
    return vtex_get(f"{VTEX_BASE_URL}/api/oms/pvt/orders/{order_id}")


# ── Funções de inserção no banco ─────────────────────────────
def upsert_order(conn, order: dict):
    """Insere ou atualiza TODOS os dados do pedido no banco."""
    with conn.cursor() as cur:
        # 1. Extrai totais
        totals = {t["id"]: t["value"] for t in (order.get("totals") or [])}

        # 2. Extrair o primeiro logistics info para entrega
        shipping_data = order.get("shippingData") or {}
        logistics_list = shipping_data.get("logisticsInfo") or []
        first_log = logistics_list[0] if logistics_list else {}
        shipping_addr = shipping_data.get("address") or {}
        geo_coords = shipping_addr.get("geoCoordinates") or []

        # 3. Upsert principal: orders
        cur.execute("""
            INSERT INTO orders (
                order_id, sequence, marketplace_order_id, seller_order_id,
                origin, affiliate_id, sales_channel, merchant_name, status,
                status_description, workflow_is_in_error, value, creation_date,
                last_change, order_group, hostname, is_completed, authorized_date,
                invoiced_date, cancel_reason, checked_in_pickup_point_id, is_checked_in,
                allow_cancellation, allow_edition, rounding_error, order_form_id,
                creation_environment, total_items, total_discounts, total_shipping,
                total_tax, raw_json, updated_at
            ) VALUES (
                %s,%s,%s,%s, %s,%s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,NOW()
            )
            ON CONFLICT (order_id) DO UPDATE SET
                status = EXCLUDED.status,
                status_description = EXCLUDED.status_description,
                last_change = EXCLUDED.last_change,
                is_completed = EXCLUDED.is_completed,
                invoiced_date = EXCLUDED.invoiced_date,
                cancel_reason = EXCLUDED.cancel_reason,
                value = EXCLUDED.value,
                total_items = EXCLUDED.total_items,
                total_discounts = EXCLUDED.total_discounts,
                total_shipping = EXCLUDED.total_shipping,
                total_tax = EXCLUDED.total_tax,
                raw_json = EXCLUDED.raw_json,
                updated_at = NOW()
        """, (
            order.get("orderId"),
            order.get("sequence"),
            order.get("marketplaceOrderId"),
            order.get("sellerOrderId"),
            order.get("origin"),
            order.get("affiliateId"),
            order.get("salesChannel"),
            order.get("merchantName"),
            order.get("status"),
            order.get("statusDescription"),
            order.get("workflowIsInError", False),
            order.get("value", 0),
            order.get("creationDate"),
            order.get("lastChange"),
            order.get("orderGroup"),
            order.get("hostname"),
            order.get("isCompleted", False),
            order.get("authorizedDate"),
            order.get("invoicedDate"),
            order.get("cancelReason"),
            order.get("checkedInPickupPointId"),
            order.get("isCheckedIn", False),
            order.get("allowCancellation", False),
            order.get("allowEdition", False),
            order.get("roundingError", 0),
            order.get("orderFormId"),
            order.get("creationEnvironment"),
            totals.get("Items", 0),
            totals.get("Discounts", 0),
            totals.get("Shipping", 0),
            totals.get("Tax", 0),
            json.dumps(order, ensure_ascii=False),
        ))

        order_id = order.get("orderId")

        # 4. Upsert marketing
        mkt = order.get("marketingData") or {}
        cur.execute("""
            INSERT INTO order_marketing (
                order_id, utm_source, utm_medium, utm_campaign, utm_partner,
                utmi_campaign, utmi_page, utmi_part, coupon, marketing_tags
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (order_id) DO UPDATE SET
                utm_source = EXCLUDED.utm_source,
                utm_medium = EXCLUDED.utm_medium,
                utm_campaign = EXCLUDED.utm_campaign,
                utm_partner = EXCLUDED.utm_partner,
                utmi_campaign = EXCLUDED.utmi_campaign,
                utmi_page = EXCLUDED.utmi_page,
                utmi_part = EXCLUDED.utmi_part,
                coupon = EXCLUDED.coupon,
                marketing_tags = EXCLUDED.marketing_tags
        """, (
            order_id,
            mkt.get("utmSource"), mkt.get("utmMedium"), mkt.get("utmCampaign"),
            mkt.get("utmPartner"), mkt.get("utmiCampaign"), mkt.get("utmipage"),
            mkt.get("utmiPart"), mkt.get("coupon"),
            json.dumps(mkt.get("marketingTags") or [], ensure_ascii=False),
        ))

        # 5. Upsert client
        client = order.get("clientProfileData") or {}
        pref = order.get("clientPreferencesData") or {}
        cur.execute("""
            INSERT INTO order_client (
                order_id, email, first_name, last_name, document_type, document,
                phone, is_corporate, corporate_name, corporate_document,
                user_profile_id, customer_class, customer_code, locale, optin_newsletter
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (order_id) DO UPDATE SET
                email = EXCLUDED.email, first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name
        """, (
            order_id,
            client.get("email"), client.get("firstName"), client.get("lastName"),
            client.get("documentType"), client.get("document"), client.get("phone"),
            client.get("isCorporate", False), client.get("corporateName"),
            client.get("corporateDocument"), client.get("userProfileId"),
            client.get("customerClass"), client.get("customerCode"),
            pref.get("locale"), pref.get("optinNewsLetter", False),
        ))

        # 6. Upsert shipping
        pickup_name = None
        if first_log.get("pickupStoreInfo"):
            pickup_name = first_log["pickupStoreInfo"].get("friendlyName")

        cur.execute("""
            INSERT INTO order_shipping (
                order_id, city, state, country, postal_code, neighborhood, street,
                geo_latitude, geo_longitude, selected_sla, delivery_channel,
                shipping_estimate, shipping_price, pickup_store_name, pickup_point_id
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (order_id) DO UPDATE SET
                selected_sla = EXCLUDED.selected_sla,
                delivery_channel = EXCLUDED.delivery_channel,
                shipping_price = EXCLUDED.shipping_price
        """, (
            order_id,
            shipping_addr.get("city"), shipping_addr.get("state"),
            shipping_addr.get("country"), shipping_addr.get("postalCode"),
            shipping_addr.get("neighborhood"), shipping_addr.get("street"),
            geo_coords[1] if len(geo_coords) > 1 else None,  # lat
            geo_coords[0] if len(geo_coords) > 0 else None,  # lon
            first_log.get("selectedSla"),
            first_log.get("selectedDeliveryChannel"),
            first_log.get("shippingEstimate"),
            first_log.get("price", 0),
            pickup_name,
            first_log.get("pickupPointId"),
        ))

        # 7. Itens — apaga e reinserir para garantir consistência
        cur.execute("DELETE FROM order_items WHERE order_id = %s", (order_id,))
        items = order.get("items") or []
        for item in items:
            add_info = item.get("additionalInfo") or {}
            cats = add_info.get("categories") or []
            cur.execute("""
                INSERT INTO order_items (
                    order_id, unique_id, sku_id, product_id, name, ref_id, ean,
                    price, list_price, selling_price, manual_price, cost_price,
                    quantity, tax, commission, freight_commission, shipping_price,
                    reward_value, seller, seller_sku, brand_name, brand_id,
                    category_ids, categories_json, is_gift, image_url, detail_url,
                    measurement_unit, unit_multiplier, price_tags_json, price_definition_json
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s
                )
            """, (
                order_id,
                item.get("uniqueId"), item.get("id"), item.get("productId"),
                item.get("name"), item.get("refId"), item.get("ean"),
                item.get("price", 0), item.get("listPrice", 0), item.get("sellingPrice", 0),
                item.get("manualPrice"), item.get("costPrice"),
                item.get("quantity", 1), item.get("tax", 0),
                item.get("commission", 0), item.get("freightCommission", 0),
                item.get("shippingPrice"),
                item.get("rewardValue", 0),
                item.get("seller"), item.get("sellerSku"),
                add_info.get("brandName"), add_info.get("brandId"),
                add_info.get("categoriesIds"),
                json.dumps(cats, ensure_ascii=False),
                item.get("isGift", False),
                item.get("imageUrl"), item.get("detailUrl"),
                item.get("measurementUnit"), item.get("unitMultiplier", 1),
                json.dumps(item.get("priceTags") or [], ensure_ascii=False),
                json.dumps(item.get("priceDefinition") or {}, ensure_ascii=False),
            ))

        # 8. Pagamentos
        cur.execute("DELETE FROM order_payments WHERE order_id = %s", (order_id,))
        pay_data = order.get("paymentData") or {}
        for txn in (pay_data.get("transactions") or []):
            for payment in (txn.get("payments") or []):
                cur.execute("""
                    INSERT INTO order_payments (
                        order_id, transaction_id, payment_id, payment_system,
                        payment_system_name, value, installments, reference_value,
                        group_name, tid, first_digits, last_digits,
                        connector_responses
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    order_id,
                    txn.get("transactionId"),
                    payment.get("id"),
                    payment.get("paymentSystem"),
                    payment.get("paymentSystemName"),
                    payment.get("value", 0),
                    payment.get("installments", 1),
                    payment.get("referenceValue", 0),
                    payment.get("group"),
                    payment.get("tid"),
                    payment.get("firstDigits"),
                    payment.get("lastDigits"),
                    json.dumps(payment.get("connectorResponses") or {}, ensure_ascii=False),
                ))

        # 9. Sellers
        cur.execute("DELETE FROM order_sellers WHERE order_id = %s", (order_id,))
        for seller in (order.get("sellers") or []):
            cur.execute("""
                INSERT INTO order_sellers (order_id, seller_id, seller_name, logo)
                VALUES (%s,%s,%s,%s)
            """, (order_id, seller.get("id"), seller.get("name"), seller.get("logo")))

        # 10. Promoções
        cur.execute("DELETE FROM order_promotions WHERE order_id = %s", (order_id,))
        rnb = order.get("ratesAndBenefitsData") or {}
        for promo in (rnb.get("rateAndBenefitsIdentifiers") or []):
            cur.execute("""
                INSERT INTO order_promotions (order_id, promotion_id, promotion_name, description, is_featured, matched_params)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                order_id,
                promo.get("id"), promo.get("name"), promo.get("description"),
                promo.get("featured", False),
                json.dumps(promo.get("matchedParameters") or {}, ensure_ascii=False),
            ))

        # 11. Atualizar channel_type na tabela orders
        origin_raw = order.get("origin") or ""
        sales_ch = order.get("salesChannel") or ""
        # Buscar mapeamento existente
        cur.execute(
            "SELECT channel_type FROM channels WHERE origin_raw = %s",
            (origin_raw,)
        )
        row = cur.fetchone()
        channel_type = row[0] if row else "Não mapeado"

        # Inserir canal se não existir
        cur.execute("""
            INSERT INTO channels (origin_raw, sales_channel, channel_type)
            VALUES (%s, %s, 'Não mapeado')
            ON CONFLICT (origin_raw) DO NOTHING
        """, (origin_raw, sales_ch))

        cur.execute(
            "UPDATE orders SET channel_type = %s WHERE order_id = %s",
            (channel_type, order_id)
        )


def update_sync_log(conn, sync_type: str, status: str, count: int, error: str = None):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sync_logs (type, status, records_processed, error_message)
            VALUES (%s, %s, %s, %s)
        """, (sync_type, status, count, error))
    conn.commit()


# ── Carga Histórica ──────────────────────────────────────────
def run_historical_load():
    log.info("=" * 60)
    log.info("INICIANDO CARGA HISTÓRICA")
    log.info("=" * 60)

    conn = get_conn()
    conn.autocommit = False

    start_date = datetime.strptime(HIST_START, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.now(timezone.utc)
    total_processed = 0

    # Iterar DIA a DIA do mais recente ao mais antigo (evita limite de 30 páginas)
    current_end = end_date
    while current_end > start_date:
        current_start = max(current_end - timedelta(days=1), start_date)
        log.info(f"\nJanela: {current_start.strftime('%Y-%m-%d %H:%M')} -> {current_end.strftime('%Y-%m-%d %H:%M')}")

        order_ids = list_orders_by_window(current_start, current_end)
        log.info(f"  {len(order_ids)} pedidos encontrados na janela")

        batch_count = 0
        for order_id in order_ids:
            order = fetch_order(order_id)
            if not order:
                log.warning(f"  Falha ao buscar pedido {order_id}")
                continue
            try:
                upsert_order(conn, order)
                conn.commit()
                batch_count += 1
                total_processed += 1
                if batch_count % 50 == 0:
                    log.info(f"  OK {batch_count}/{len(order_ids)} pedidos processados")
            except psycopg2.OperationalError as e:
                log.error(f"  Erro de conexao: {e}. Tentando reconectar...")
                try:
                    conn.close()
                except:
                    pass
                conn = get_conn()
                conn.autocommit = False
                try:
                    upsert_order(conn, order)
                    conn.commit()
                    batch_count += 1
                    total_processed += 1
                except Exception as e2:
                    conn.rollback()
                    log.error(f"  Erro no pedido {order_id} apos reconectar: {e2}")
            except Exception as e:
                try:
                    conn.rollback()
                except:
                    pass
                log.error(f"  Erro no pedido {order_id}: {e}")

        log.info(f"  Janela concluída: {batch_count} pedidos inseridos")
        current_end = current_start

    update_sync_log(conn, "historical", "success", total_processed)
    conn.close()

    log.info(f"\nCARGA HISTÓRICA CONCLUÍDA — {total_processed} pedidos processados")


if __name__ == "__main__":
    run_historical_load()
