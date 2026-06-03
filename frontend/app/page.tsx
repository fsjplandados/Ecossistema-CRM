"use client";

import { useState, useEffect, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";
import KPICard from "@/components/KPICard";
import MultiSelectFilter from "@/components/MultiSelectFilter";
import CategoryTable from "@/components/CategoryTable";
import TopProductsList from "@/components/TopProductsList";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Formatadores ─────────────────────────────────────────── */
const fmtBRL = (v: number) =>
  v >= 1000 ? `R$ ${(v / 1000).toFixed(0)} mil` : `R$ ${v.toFixed(0)}`;

const fmtBRLFull = (v: number) =>
  v.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  });

const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const dateOffset = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/* ── Tooltip customizado ──────────────────────────────────── */
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div
        style={{
          background: "#fff",
          border: "1px solid #E2E8F0",
          borderRadius: 10,
          padding: "12px 16px",
          boxShadow: "0 4px 20px rgba(0,0,0,0.10)",
          fontFamily: "Inter, sans-serif",
        }}
      >
        <div
          style={{
            fontFamily: "Montserrat, sans-serif",
            fontWeight: 700,
            fontSize: 13,
            marginBottom: 8,
            color: "#111827",
          }}
        >
          {label}
        </div>
        {payload.map(
          (p: any) =>
            p.value != null && (
              <div
                key={p.dataKey}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginBottom: 4,
                }}
              >
                <div
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    background: p.color,
                  }}
                />
                <span style={{ fontSize: 12, color: "#6B7280" }}>
                  {p.name}:
                </span>
                <span
                  style={{ fontSize: 12, fontWeight: 600, color: "#111827" }}
                >
                  {fmtBRL(p.value)}
                </span>
              </div>
            )
        )}
      </div>
    );
  }
  return null;
};

/* ── Página principal ─────────────────────────────────────── */
export default function PerformancePage() {
  const [dateFrom, setDateFrom] = useState(todayStr());
  const [dateTo, setDateTo] = useState(todayStr());

  // Multi-select filter states (arrays)
  const [selChannels, setSelChannels] = useState<string[]>([]);
  const [selBrands, setSelBrands] = useState<string[]>([]);
  const [selCategories, setSelCategories] = useState<string[]>([]);
  const [selUtmSources, setSelUtmSources] = useState<string[]>([]);
  const [selUtmCampaigns, setSelUtmCampaigns] = useState<string[]>([]);
  const [selUtmMediums, setSelUtmMediums] = useState<string[]>([]);
  const [selUtmiParts, setSelUtmiParts] = useState<string[]>([]);

  const [selectedCategoryRow, setSelectedCategoryRow] = useState<string | null>(null);
  const [drillDownData, setDrillDownData] = useState<any[]>([]);
  const [drillDownLoading, setDrillDownLoading] = useState(false);
  const [syncTime, setSyncTime] = useState<string | null>(null);

  const [selectedHour, setSelectedHour] = useState<string | null>(null);
  const [catData, setCatData] = useState<any[]>([]);
  const [catLoading, setCatLoading] = useState(false);
  const [prodData, setProdData] = useState<any[]>([]);
  const [prodLoading, setProdLoading] = useState(false);

  const [loading, setLoading] = useState(false);
  const [chartData, setChartData] = useState<any[]>([]);
  const [kpis, setKpis] = useState({
    total_revenue: 0,
    total_orders: 0,
    avg_ticket: 0,
    approved_revenue: 0,
    canceled_orders: 0,
    yesterday_revenue: 0,
    avg7d_revenue: 0,
    yesterday_orders: 0,
    avg7d_orders: 0,
    yesterday_ticket: 0,
    avg7d_ticket: 0,
  });
  const [filters, setFilters] = useState<any>({
    channels: [],
    brands: [],
    categories: [],
    utm_sources: [],
    utm_campaigns: [],
    utm_mediums: [],
    utmi_parts: [],
  });

  /* ── Carrega filtros disponíveis ──────────────────────────── */
  useEffect(() => {
    fetch(`${API_URL}/api/dashboard/filters`)
      .then((r) => r.json())
      .then(setFilters)
      .catch(() => { });
  }, []);

  /* ── Helper: monta mapa hora a hora (24h) ─────────────────── */
  const buildHourlyMap = (data: any[]) => {
    const map: Record<string, number> = {};
    data.forEach((d) => {
      if (d.hour_label) map[d.hour_label] = d.total_revenue;
    });
    return Array.from({ length: 24 }, (_, i) => {
      const label = `${String(i).padStart(2, "0")}:00`;
      return { hour: label, value: map[label] ?? null };
    });
  };

  /* ── Helper: cria params de filtro ────────────────────────── */
  const appendFilters = (p: URLSearchParams) => {
    if (selChannels.length) p.append("channel", selChannels.join(","));
    if (selBrands.length) p.append("brand", selBrands.join(","));
    if (selCategories.length) p.append("category", selCategories.join(","));
    if (selUtmSources.length) p.append("utm_source", selUtmSources.join(","));
    if (selUtmCampaigns.length) p.append("utm_campaign", selUtmCampaigns.join(","));
    if (selUtmMediums.length) p.append("utm_medium", selUtmMediums.join(","));
    if (selUtmiParts.length) p.append("utmi_part", selUtmiParts.join(","));
  };

  /* ── Fetch principal ──────────────────────────────────────── */
  const fetchData = useCallback(async () => {
    setLoading(true);
    setCatLoading(true);
    try {
      // Params do período selecionado
      const p = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      appendFilters(p);

      // ── Busca em paralelo: dados do período + KPIs + Categorias ──
      const [revRes, kpiRes, catRes] = await Promise.all([
        fetch(`${API_URL}/api/dashboard/hourly-revenue?${p}`),
        fetch(`${API_URL}/api/dashboard/kpis?${p}`),
        fetch(`${API_URL}/api/dashboard/categories-performance?${p}`)
      ]);
      const revData = await revRes.json();
      const kpiData = await kpiRes.json();
      const catData = await catRes.json();

      // ── Busca dados de ontem (para o gráfico) ──
      const ydP = new URLSearchParams({
        date_from: dateOffset(-1),
        date_to: dateOffset(-1),
      });
      appendFilters(ydP);
      const ydRes = await fetch(
        `${API_URL}/api/dashboard/hourly-revenue?${ydP}`
      );
      const ydData = await ydRes.json();

      // ── Busca dados média 7 dias (para o gráfico) ──
      const avg7dP = new URLSearchParams({
        date_from: dateOffset(-7),
        date_to: dateOffset(-1),
      });
      appendFilters(avg7dP);
      const avg7dRes = await fetch(
        `${API_URL}/api/dashboard/hourly-revenue?${avg7dP}`
      );
      const avg7dRaw = await avg7dRes.json();

      // ── Mapear dados hora a hora ──
      const todayMap = buildHourlyMap(revData.data || []);
      const ydMap = buildHourlyMap(ydData.data || []);

      // Média 7 dias: agrupar por hora e calcular média
      const avg7dByHour: Record<string, number[]> = {};
      (avg7dRaw.data || []).forEach((d: any) => {
        if (d.hour_label) {
          if (!avg7dByHour[d.hour_label]) avg7dByHour[d.hour_label] = [];
          avg7dByHour[d.hour_label].push(d.total_revenue);
        }
      });
      const avg7dMap = Array.from({ length: 24 }, (_, i) => {
        const label = `${String(i).padStart(2, "0")}:00`;
        const vals = avg7dByHour[label] || [];
        return {
          hour: label,
          value:
            vals.length > 0
              ? vals.reduce((a, b) => a + b, 0) / 7
              : null,
        };
      });

      // ── Montar dados do gráfico ──
      setChartData(
        todayMap.map((h, i) => ({
          hour: h.hour,
          hoje: h.value,
          ontem: ydMap[i]?.value ?? null,
          media7d: avg7dMap[i]?.value ?? null,
        }))
      );

      // Fetch Sync Status
      fetch(`${API_URL}/api/sync/status`)
        .then(r => r.json())
        .then(data => setSyncTime(data.last_sync))
        .catch(() => {});

      setKpis(kpiData);
      setCatData(catData);
    } catch (err) {
      console.error("Erro ao buscar dados:", err);
    } finally {
      setLoading(false);
      setCatLoading(false);
    }
  }, [dateFrom, dateTo, selChannels, selBrands, selCategories, selUtmSources, selUtmCampaigns, selUtmMediums, selUtmiParts]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fetchTopProducts = useCallback(async () => {
    setProdLoading(true);
    try {
      const p = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      appendFilters(p);
      if (selectedHour) p.append("hour", selectedHour);
      if (selectedCategoryRow) p.append("category", selectedCategoryRow);
      const res = await fetch(`${API_URL}/api/dashboard/top-products?${p}`);
      const data = await res.json();
      setProdData(data);
    } catch (e) {
      console.error(e);
    } finally {
      setProdLoading(false);
    }
  }, [dateFrom, dateTo, selChannels, selBrands, selCategories, selUtmSources, selUtmCampaigns, selUtmMediums, selUtmiParts, selectedHour, selectedCategoryRow]);

  useEffect(() => {
    fetchTopProducts();
  }, [fetchTopProducts]);

  const fetchDrillDown = useCallback(async () => {
    if (!selectedCategoryRow) return;
    setDrillDownLoading(true);
    try {
      const p = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      appendFilters(p);
      p.append("category", selectedCategoryRow);
      const res = await fetch(`${API_URL}/api/dashboard/products-performance?${p}`);
      const data = await res.json();
      setDrillDownData(data);
    } catch (e) {
      console.error(e);
    } finally {
      setDrillDownLoading(false);
    }
  }, [dateFrom, dateTo, selChannels, selBrands, selCategories, selUtmSources, selUtmCampaigns, selUtmMediums, selUtmiParts, selectedCategoryRow]);

  useEffect(() => {
    fetchDrillDown();
  }, [fetchDrillDown]);

  /* ── Delta % ──────────────────────────────────────────────── */
  const pct = (current: number, prev: number) =>
    prev > 0 ? ((current - prev) / prev) * 100 : null;

  return (
    <>
      <Header />
      <Sidebar />

      <div className="main-layout">
        <div className="page-content">
          {/* ── Cabeçalho ──────────────────────────────────── */}
          <div style={{ marginBottom: 20 }}>
            <div className="page-title">
              <span style={{ marginRight: 8 }}>🛒</span>
              VTEX — Performance de Vendas
            </div>
            <div className="page-subtitle">
              Faturamento Hora a Hora ·{" "}
              {new Date().toLocaleDateString("pt-BR", {
                weekday: "long",
                day: "2-digit",
                month: "long",
                year: "numeric",
              })}
            </div>
          </div>

          {/* ── Barra de filtros ───────────────────────────── */}
          <div className="filter-bar">
            <div className="filter-group">
              <label className="filter-label">De</label>
              <input
                type="date"
                className="filter-input"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div className="filter-group">
              <label className="filter-label">Até</label>
              <input
                type="date"
                className="filter-input"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
            <MultiSelectFilter
              label="Canal"
              options={filters.channels || []}
              selected={selChannels}
              onChange={setSelChannels}
              placeholder="Todos"
            />
            <MultiSelectFilter
              label="Categoria"
              options={filters.categories || []}
              selected={selCategories}
              onChange={setSelCategories}
              placeholder="Todas"
            />
            <MultiSelectFilter
              label="Marca"
              options={filters.brands || []}
              selected={selBrands}
              onChange={setSelBrands}
              placeholder="Todas"
            />
            <MultiSelectFilter
              label="UTM Source"
              options={filters.utm_sources || []}
              selected={selUtmSources}
              onChange={setSelUtmSources}
              placeholder="Todos"
            />
            <MultiSelectFilter
              label="UTM Campaign"
              options={filters.utm_campaigns || []}
              selected={selUtmCampaigns}
              onChange={setSelUtmCampaigns}
              placeholder="Todas"
            />
            <MultiSelectFilter
              label="UTM Medium"
              options={filters.utm_mediums || []}
              selected={selUtmMediums}
              onChange={setSelUtmMediums}
              placeholder="Todos"
            />
            <MultiSelectFilter
              label="UTMI Part"
              options={filters.utmi_parts || []}
              selected={selUtmiParts}
              onChange={setSelUtmiParts}
              placeholder="Todos"
            />
            <button
              className="btn-apply"
              onClick={fetchData}
              disabled={loading}
            >
              {loading ? (
                <span
                  style={{ display: "flex", alignItems: "center", gap: 8 }}
                >
                  <span
                    className="spinner"
                    style={{ width: 14, height: 14, borderWidth: 2 }}
                  />{" "}
                  Carregando...
                </span>
              ) : (
                "Aplicar Filtros"
              )}
            </button>
            <button
              className="btn-reset"
              onClick={() => {
                setDateFrom(todayStr());
                setDateTo(todayStr());
                setSelChannels([]);
                setSelBrands([]);
                setSelCategories([]);
                setSelUtmSources([]);
                setSelUtmCampaigns([]);
                setSelUtmMediums([]);
                setSelUtmiParts([]);
                setSelectedHour(null);
                setSelectedCategoryRow(null);
              }}
            >
              Limpar
            </button>
          </div>

          {/* ── KPI Cards ──────────────────────────────────── */}
          <div className="kpi-grid">
            <KPICard
              type="receita"
              label="Faturamento Total"
              value={fmtBRLFull(kpis.total_revenue)}
              yoy={pct(kpis.total_revenue, kpis.yesterday_revenue)}
              mom={pct(kpis.total_revenue, kpis.avg7d_revenue)}
              yesterday={fmtBRLFull(kpis.yesterday_revenue)}
              avg7d={fmtBRLFull(kpis.avg7d_revenue)}
            />
            <KPICard
              type="pedidos"
              label="Pedidos"
              value={kpis.total_orders.toLocaleString("pt-BR")}
              yoy={pct(kpis.total_orders, kpis.yesterday_orders)}
              mom={pct(kpis.total_orders, kpis.avg7d_orders)}
              yesterday={kpis.yesterday_orders.toLocaleString("pt-BR")}
              avg7d={kpis.avg7d_orders.toLocaleString("pt-BR")}
            />
            <KPICard
              type="ticket"
              label="Ticket Médio"
              value={fmtBRLFull(kpis.avg_ticket)}
              yoy={pct(kpis.avg_ticket, kpis.yesterday_ticket)}
              mom={pct(kpis.avg_ticket, kpis.avg7d_ticket)}
              yesterday={fmtBRLFull(kpis.yesterday_ticket)}
              avg7d={fmtBRLFull(kpis.avg7d_ticket)}
            />
            <KPICard
              type="aprovado"
              label="Receita Aprovada"
              value={fmtBRLFull(kpis.approved_revenue)}
            />
            <KPICard
              type="cancelados"
              label="Cancelamentos"
              value={kpis.canceled_orders.toLocaleString("pt-BR")}
            />
          </div>

          {/* ── Gráfico ────────────────────────────────────── */}
          <div className="chart-card">
            <div className="chart-header">
              <div>
                <div className="chart-title">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#007BFF"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    style={{ flexShrink: 0 }}
                  >
                    <circle cx="9" cy="21" r="1" />
                    <circle cx="20" cy="21" r="1" />
                    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
                  </svg>
                  VTEX — PERFORMANCE DE VENDAS
                </div>
                <div className="chart-subtitle">
                  Faturamento Hora a Hora (Dados Reais)
                </div>
              </div>
              {loading && <div className="spinner" />}
            </div>

            <ResponsiveContainer width="100%" height={320}>
              <LineChart
                data={chartData}
                margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
                onClick={(e: any) => {
                  if (e && e.activeLabel) {
                    setSelectedHour(e.activeLabel);
                  }
                }}
              >
                <CartesianGrid
                  strokeDasharray="4 4"
                  stroke="#F3F4F6"
                  vertical={false}
                />
                <XAxis
                  dataKey="hour"
                  tick={{
                    fontFamily: "Inter",
                    fontSize: 11,
                    fill: "#9CA3AF",
                  }}
                  tickLine={false}
                  axisLine={{ stroke: "#E5E7EB" }}
                  interval={1}
                />
                <YAxis
                  tickFormatter={(v) =>
                    v >= 1000 ? `${(v / 1000).toFixed(0)} mil` : `${v}`
                  }
                  tick={{
                    fontFamily: "Inter",
                    fontSize: 11,
                    fill: "#9CA3AF",
                  }}
                  tickLine={false}
                  axisLine={false}
                  width={70}
                />
                <Tooltip content={<CustomTooltip />} />

                <Line
                  type="monotone"
                  dataKey="hoje"
                  name="Hoje"
                  stroke="#007BFF"
                  strokeWidth={2}
                  dot={{
                    r: 4,
                    fill: "#007BFF",
                    strokeWidth: 2,
                    stroke: "#fff",
                  }}
                  activeDot={{ r: 6 }}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="media7d"
                  name="Média 7 Dias"
                  stroke="#D1D5DB"
                  strokeWidth={1.5}
                  strokeDasharray="3 5"
                  dot={false}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="ontem"
                  name="Ontem"
                  stroke="#9CA3AF"
                  strokeWidth={1.5}
                  strokeDasharray="6 3"
                  dot={false}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>

            {/* Legenda */}
            <div className="chart-legend">
              <div className="legend-item">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                  }}
                >
                  <div
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: "#007BFF",
                      border: "2px solid #fff",
                      boxShadow: "0 0 0 1.5px #007BFF",
                    }}
                  />
                  <div
                    style={{
                      width: 20,
                      height: 2,
                      background: "#007BFF",
                      borderRadius: 2,
                    }}
                  />
                </div>
                <span>Hoje</span>
              </div>
              <div className="legend-item">
                <div
                  style={{
                    width: 26,
                    height: 0,
                    borderTop: "2px dashed #D1D5DB",
                  }}
                />
                <span>Média 7 Dias</span>
              </div>
              <div className="legend-item">
                <div
                  style={{
                    width: 26,
                    height: 0,
                    borderTop: "2px dashed #9CA3AF",
                  }}
                />
                <span>Ontem</span>
              </div>
            </div>
          </div>

          <div className="layout-grid">
            {selectedCategoryRow ? (
              <CategoryTable 
                data={drillDownData} 
                loading={drillDownLoading} 
                isProductMode={true}
                onBack={() => setSelectedCategoryRow(null)}
              />
            ) : (
              <CategoryTable 
                data={catData} 
                loading={catLoading} 
                onSelectCategory={setSelectedCategoryRow}
              />
            )}
            <TopProductsList 
              data={prodData} 
              loading={prodLoading} 
              selectedHour={selectedHour}
              selectedCategory={selectedCategoryRow}
              onClearHour={() => setSelectedHour(null)}
              onClearCategory={() => setSelectedCategoryRow(null)}
            />
          </div>

          <div
            style={{
              textAlign: "center",
              fontFamily: "Inter",
              fontSize: 11,
              color: "#D1D5DB",
              marginTop: 16,
            }}
          >
            Dados sincronizados automaticamente a cada hora · Fonte: VTEX OMS
            {syncTime && (
              <div style={{ marginTop: 4 }}>
                Atualizado às {new Date(syncTime).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
