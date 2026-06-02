-- ============================================================
-- SCHEMA COMPLETO — Dashboard de Faturamento VTEX
-- NeonDB (PostgreSQL Serverless)
-- ============================================================

-- Tabela de controle de sincronização
CREATE TABLE IF NOT EXISTS sync_logs (
    id              SERIAL PRIMARY KEY,
    execution_time  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    records_processed INTEGER DEFAULT 0,
    status          VARCHAR(50) NOT NULL,  -- 'success', 'error', 'running'
    type            VARCHAR(20) NOT NULL,  -- 'historical', 'delta'
    last_order_date TIMESTAMPTZ,
    error_message   TEXT
);

-- Tabela de mapeamento de canais (Site vs App)
CREATE TABLE IF NOT EXISTS channels (
    id           SERIAL PRIMARY KEY,
    origin_raw   VARCHAR(255) UNIQUE NOT NULL,
    sales_channel VARCHAR(50),
    channel_type VARCHAR(20) DEFAULT 'Não mapeado',  -- 'Site', 'App', 'Não mapeado'
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela principal de pedidos (dados completos)
CREATE TABLE IF NOT EXISTS orders (
    order_id                  VARCHAR(100) PRIMARY KEY,
    sequence                  VARCHAR(50),
    marketplace_order_id      VARCHAR(255),
    seller_order_id           VARCHAR(255),
    origin                    VARCHAR(100),
    affiliate_id              VARCHAR(100),
    sales_channel             VARCHAR(50),
    merchant_name             VARCHAR(255),
    status                    VARCHAR(100) NOT NULL,
    status_description        VARCHAR(255),
    workflow_is_in_error      BOOLEAN DEFAULT FALSE,
    value                     INTEGER NOT NULL DEFAULT 0,   -- em centavos
    creation_date             TIMESTAMPTZ NOT NULL,
    last_change               TIMESTAMPTZ,
    order_group               VARCHAR(100),
    hostname                  VARCHAR(255),
    is_completed              BOOLEAN DEFAULT FALSE,
    authorized_date           TIMESTAMPTZ,
    invoiced_date             TIMESTAMPTZ,
    cancel_reason             TEXT,
    checked_in_pickup_point_id VARCHAR(255),
    is_checked_in             BOOLEAN DEFAULT FALSE,
    allow_cancellation        BOOLEAN DEFAULT FALSE,
    allow_edition             BOOLEAN DEFAULT FALSE,
    rounding_error            INTEGER DEFAULT 0,
    order_form_id             VARCHAR(100),
    creation_environment      VARCHAR(100),
    total_items               INTEGER DEFAULT 0,
    total_discounts           INTEGER DEFAULT 0,
    total_shipping            INTEGER DEFAULT 0,
    total_tax                 INTEGER DEFAULT 0,
    channel_type              VARCHAR(20) DEFAULT 'Não mapeado',  -- 'Site', 'App'
    raw_json                  JSONB,  -- backup do JSON completo
    synced_at                 TIMESTAMPTZ DEFAULT NOW(),
    updated_at                TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de itens dos pedidos
CREATE TABLE IF NOT EXISTS order_items (
    id                SERIAL PRIMARY KEY,
    order_id          VARCHAR(100) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    unique_id         VARCHAR(100),
    sku_id            VARCHAR(100),
    product_id        VARCHAR(100),
    name              TEXT,
    ref_id            VARCHAR(100),
    ean               VARCHAR(50),
    price             INTEGER DEFAULT 0,
    list_price        INTEGER DEFAULT 0,
    selling_price     INTEGER DEFAULT 0,
    manual_price      INTEGER,
    manual_price_applied_by VARCHAR(255),
    cost_price        INTEGER,
    quantity          INTEGER DEFAULT 1,
    tax               INTEGER DEFAULT 0,
    tax_code          VARCHAR(100),
    commission        INTEGER DEFAULT 0,
    freight_commission INTEGER DEFAULT 0,
    shipping_price    INTEGER,
    reward_value      INTEGER DEFAULT 0,
    seller            VARCHAR(255),
    seller_sku        VARCHAR(100),
    brand_name        VARCHAR(255),
    brand_id          VARCHAR(100),
    category_ids      VARCHAR(500),
    categories_json   JSONB,
    is_gift           BOOLEAN DEFAULT FALSE,
    image_url         TEXT,
    detail_url        TEXT,
    measurement_unit  VARCHAR(20),
    unit_multiplier   NUMERIC(10,4) DEFAULT 1,
    price_tags_json   JSONB,
    price_definition_json JSONB,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de dados de marketing / UTMs
CREATE TABLE IF NOT EXISTS order_marketing (
    order_id      VARCHAR(100) PRIMARY KEY REFERENCES orders(order_id) ON DELETE CASCADE,
    utm_source    VARCHAR(255),
    utm_medium    VARCHAR(255),
    utm_campaign  VARCHAR(255),
    utm_partner   VARCHAR(255),
    utmi_campaign VARCHAR(255),
    utmi_page     VARCHAR(255),
    utmi_part     VARCHAR(255),
    coupon        VARCHAR(255),
    marketing_tags JSONB,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de dados de pagamento
CREATE TABLE IF NOT EXISTS order_payments (
    id                  SERIAL PRIMARY KEY,
    order_id            VARCHAR(100) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    transaction_id      VARCHAR(255),
    payment_id          VARCHAR(255),
    payment_system      VARCHAR(50),
    payment_system_name VARCHAR(255),
    value               INTEGER DEFAULT 0,
    installments        INTEGER DEFAULT 1,
    reference_value     INTEGER DEFAULT 0,
    group_name          VARCHAR(100),  -- 'creditCard', 'debitCard', 'pix', etc.
    tid                 VARCHAR(255),
    first_digits        VARCHAR(20),
    last_digits         VARCHAR(10),
    bank_issued_invoice_barcode VARCHAR(500),
    gift_card_id        VARCHAR(255),
    gift_card_name      VARCHAR(255),
    payment_origin      VARCHAR(255),
    connector_responses JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de dados de entrega
CREATE TABLE IF NOT EXISTS order_shipping (
    order_id            VARCHAR(100) PRIMARY KEY REFERENCES orders(order_id) ON DELETE CASCADE,
    city                VARCHAR(255),
    state               VARCHAR(10),
    country             VARCHAR(10),
    postal_code         VARCHAR(20),
    neighborhood        VARCHAR(255),
    street              VARCHAR(500),
    geo_latitude        NUMERIC(12,8),
    geo_longitude       NUMERIC(12,8),
    selected_sla        VARCHAR(255),
    delivery_channel    VARCHAR(100),  -- 'delivery', 'pickup-in-point'
    shipping_estimate   VARCHAR(50),
    shipping_price      INTEGER DEFAULT 0,
    pickup_store_name   VARCHAR(255),
    pickup_point_id     VARCHAR(255),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de perfil do cliente
CREATE TABLE IF NOT EXISTS order_client (
    order_id          VARCHAR(100) PRIMARY KEY REFERENCES orders(order_id) ON DELETE CASCADE,
    email             VARCHAR(500),
    first_name        VARCHAR(255),
    last_name         VARCHAR(255),
    document_type     VARCHAR(20),
    document          VARCHAR(100),
    phone             VARCHAR(50),
    is_corporate      BOOLEAN DEFAULT FALSE,
    corporate_name    VARCHAR(255),
    corporate_document VARCHAR(100),
    user_profile_id   VARCHAR(255),
    customer_class    VARCHAR(100),
    customer_code     VARCHAR(100),
    locale            VARCHAR(20),
    optin_newsletter  BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de sellers / franquias
CREATE TABLE IF NOT EXISTS order_sellers (
    id          SERIAL PRIMARY KEY,
    order_id    VARCHAR(100) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    seller_id   VARCHAR(255),
    seller_name VARCHAR(500),
    logo        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de promoções aplicadas
CREATE TABLE IF NOT EXISTS order_promotions (
    id              SERIAL PRIMARY KEY,
    order_id        VARCHAR(100) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    promotion_id    VARCHAR(255),
    promotion_name  VARCHAR(500),
    description     TEXT,
    is_featured     BOOLEAN DEFAULT FALSE,
    matched_params  JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de totais do pedido (detalhado)
CREATE TABLE IF NOT EXISTS order_totals (
    id          SERIAL PRIMARY KEY,
    order_id    VARCHAR(100) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    total_id    VARCHAR(50),   -- 'Items', 'Discounts', 'Shipping', 'Tax'
    name        VARCHAR(255),
    value       INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ÍNDICES PARA PERFORMANCE
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_orders_creation_date ON orders(creation_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_channel_type ON orders(channel_type);
CREATE INDEX IF NOT EXISTS idx_orders_last_change ON orders(last_change);
CREATE INDEX IF NOT EXISTS idx_orders_sales_channel ON orders(sales_channel);
CREATE INDEX IF NOT EXISTS idx_orders_origin ON orders(origin);
CREATE INDEX IF NOT EXISTS idx_orders_value ON orders(value);
CREATE INDEX IF NOT EXISTS idx_orders_creation_date_status ON orders(creation_date, status);

CREATE INDEX IF NOT EXISTS idx_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_items_brand ON order_items(brand_name);
CREATE INDEX IF NOT EXISTS idx_items_product_id ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_items_sku_id ON order_items(sku_id);

CREATE INDEX IF NOT EXISTS idx_marketing_order ON order_marketing(order_id);
CREATE INDEX IF NOT EXISTS idx_marketing_utm_source ON order_marketing(utm_source);
CREATE INDEX IF NOT EXISTS idx_marketing_utm_campaign ON order_marketing(utm_campaign);
CREATE INDEX IF NOT EXISTS idx_marketing_coupon ON order_marketing(coupon);

CREATE INDEX IF NOT EXISTS idx_shipping_state ON order_shipping(state);
CREATE INDEX IF NOT EXISTS idx_shipping_city ON order_shipping(city);

-- ============================================================
-- INSERÇÃO DE VALORES PADRÃO DE CANAIS (ajustar após carga)
-- ============================================================

INSERT INTO channels (origin_raw, sales_channel, channel_type) VALUES
    ('Marketplace', '1', 'Site'),
    ('Fulfillment', '1', 'Site')
ON CONFLICT (origin_raw) DO NOTHING;
