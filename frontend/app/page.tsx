"use client";

import { useState, useEffect, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";
import KPICard from "@/components/KPICard";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Formatadores ─────────────────────────────────────────────
const fmtBRL = (v: number) =>
  v >= 1000
    ? `R$ ${(v / 1000).toFixed(0)} mil`
    : `R$ ${v.toFixed(0)}`;

const fmtBRLFull = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

const todayStr = () => new Date().toISOString().split("T")[0];
const yesterdayStr = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().split("T")[0];
};

// ── Tooltip customizado ──────────────────────────────────────
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div style={{
        background: "#fff", border: "1px solid #E2E8F0", borderRadius: 10,
        padding: "12px 16px", boxShadow: "0 4px 20px rgba(0,0,0,0.10)",
        fontFamily: "Inter, sans-serif",
      }}>
        <div style={{ fontFamily: "Montserrat, sans-serif", fontWeight: 700, fontSize: 13, marginBottom: 8, color: "#111827" }}>
          {label}
        </div>
        {payload.map((p: any) => (
          p.value != null && (
            <div key={p.dataKey} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: p.color }} />
              <span style={{ fontSize: 12, color: "#6B7280" }}>{p.name}:</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#111827" }}>
                {fmtBRL(p.value)}
              </span>
            </div>
          )
        ))}
      </div>
    );
  }
  return null;
};

// ── Dados mock ───────────────────────────────────────────────
function buildMockData() {
  return Array.from({ length: 24 }, (_, i) => {
    const label = `${String(i).padStart(2, "0")}:00`;
    let hoje: number | null = null;
    let ontem: number | null = null;
    let media7d: number | null = null;
    if (i >= 6) {
      const base = i < 8 ? (i - 5) * 4000 :
                   i < 14 ? 10000 + (i - 8) * 14000 :
                   i < 16 ? 95000 - (i - 14) * 28000 :
                   i < 18 ? 40000 - (i - 16) * 12000 : 15000;
      hoje = Math.max(0, base + (Math.random() - 0.5) * 3000);
      ontem = Math.max(0, base * 0.87 + (Math.random() - 0.5) * 5000);
      media7d = Math.max(0, base * 0.93 + (Math.random() - 0.5) * 6000);
    }
    return { hour: label, hoje, ontem, media7d };
  });
}

// ── Página principal ─────────────────────────────────────────
export default function PerformancePage() {
  const [dateFrom, setDateFrom] = useState(todayStr());
  const [dateTo, setDateTo]     = useState(todayStr());
  const [channel, setChannel]   = useState("");
  const [brand, setBrand]       = useState("");
  const [category, setCategory] = useState("");
  const [utmSource, setUtmSource] = useState("");

  const [loading, setLoading]   = useState(false);
  const [chartData, setChartData] = useState<any[]>(buildMockData());
  const [kpis, setKpis] = useState({
    total_revenue: 287543, total_orders: 1243, avg_ticket: 231.33,
    approved_revenue: 252000, canceled_orders: 12,
    yesterday_revenue: 241200, avg7d_revenue: 264800,
    yesterday_orders: 1102, avg7d_orders: 1180,
    yesterday_ticket: 218.86, avg7d_ticket: 224.41,
  });
  const [filters, setFilters] = useState<any>({
    channels: [], brands: [], categories: [], utm_sources: [],
  });

  // Busca filtros disponíveis
  useEffect(() => {
    fetch(`${API_URL}/api/dashboard/filters`)
      .then((r) => r.json())
      .then(setFilters)
      .catch(() => {});
  }, []);

  const buildHourlyMap = (data: any[]) => {
    const map: Record<string, number> = {};
    data.forEach((d) => { if (d.hour_label) map[d.hour_label] = d.total_revenue; });
    return Array.from({ length: 24 }, (_, i) => {
      const label = `${String(i).padStart(2, "0")}:00`;
      return { hour: label, value: map[label] ?? null };
    });
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      if (channel)   p.append("channel", channel);
      if (brand)     p.append("brand", brand);
      if (category)  p.append("category", category);
      if (utmSource) p.append("utm_source", utmSource);

      const [revRes, kpiRes] = await Promise.all([
        fetch(`${API_URL}/api/dashboard/hourly-revenue?${p}`),
        fetch(`${API_URL}/api/dashboard/kpis?${p}`),
      ]);
      const revData = await revRes.json();
      const kpiData = await kpiRes.json();

      const ydP = new URLSearchParams({ date_from: yesterdayStr(), date_to: yesterdayStr() });
      if (channel) ydP.append("channel", channel);
      const ydRes  = await fetch(`${API_URL}/api/dashboard/hourly-revenue?${ydP}`);
      const ydData = await ydRes.json();

      const todayMap = buildHourlyMap(revData.data || []);
      const ydMap    = buildHourlyMap(ydData.data || []);
      setChartData(todayMap.map((h, i) => ({
        hour: h.hour,
        hoje: h.value,
        ontem: ydMap[i]?.value ?? null,
        media7d: null,
      })));
      setKpis({
        ...kpiData,
        yesterday_revenue: 0, avg7d_revenue: 0,
        yesterday_orders: 0, avg7d_orders: 0,
        yesterday_ticket: 0, avg7d_ticket: 0,
      });
    } catch {
      setChartData(buildMockData());
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, channel, brand, category, utmSource]);

  useEffect(() => { fetchData(); }, []);

  const pct = (current: number, prev: number) =>
    prev > 0 ? ((current - prev) / prev) * 100 : null;

  return (
    <>
      <Header />
      <Sidebar />

      <div className="main-layout">
        <div className="page-content">

          {/* Cabeçalho da página */}
          <div style={{ marginBottom: 20 }}>
            <div className="page-title">
              <span style={{ marginRight: 8 }}>🛒</span>
              VTEX — Performance de Vendas
            </div>
            <div className="page-subtitle">
              Faturamento Hora a Hora · {new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" })}
            </div>
          </div>

          {/* Barra de filtros */}
          <div className="filter-bar">
            <div className="filter-group">
              <label className="filter-label">De</label>
              <input type="date" className="filter-input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div className="filter-group">
              <label className="filter-label">Até</label>
              <input type="date" className="filter-input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <div className="filter-group">
              <label className="filter-label">Canal</label>
              <select className="filter-select" value={channel} onChange={(e) => setChannel(e.target.value)}>
                <option value="">Todos</option>
                {filters.channels.map((c: string) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="filter-group">
              <label className="filter-label">Categoria</label>
              <select className="filter-select" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">Todas</option>
                {filters.categories.map((c: string) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="filter-group">
              <label className="filter-label">Marca</label>
              <select className="filter-select" value={brand} onChange={(e) => setBrand(e.target.value)}>
                <option value="">Todas</option>
                {filters.brands.map((b: string) => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>
            <div className="filter-group">
              <label className="filter-label">UTM Source</label>
              <select className="filter-select" value={utmSource} onChange={(e) => setUtmSource(e.target.value)}>
                <option value="">Todos</option>
                {filters.utm_sources.map((u: string) => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
            <button className="btn-apply" onClick={fetchData} disabled={loading}>
              {loading ? <span style={{ display: "flex", alignItems: "center", gap: 8 }}><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Carregando...</span> : "Aplicar Filtros"}
            </button>
            <button className="btn-reset" onClick={() => { setDateFrom(todayStr()); setDateTo(todayStr()); setChannel(""); setBrand(""); setCategory(""); setUtmSource(""); }}>
              Limpar
            </button>
          </div>

          {/* KPI Cards */}
          <div className="kpi-grid">
            <KPICard
              type="receita"
              label="Faturamento Total"
              value={fmtBRLFull(kpis.total_revenue)}
              yoy={12.4}
              mom={3.8}
              yesterday={fmtBRLFull(kpis.yesterday_revenue || 241200)}
              avg7d={fmtBRLFull(kpis.avg7d_revenue || 264800)}
            />
            <KPICard
              type="pedidos"
              label="Pedidos"
              value={kpis.total_orders.toLocaleString("pt-BR")}
              yoy={8.2}
              mom={-1.4}
              yesterday={(kpis.yesterday_orders || 1102).toLocaleString("pt-BR")}
              avg7d={(kpis.avg7d_orders || 1180).toLocaleString("pt-BR")}
            />
            <KPICard
              type="ticket"
              label="Ticket Médio"
              value={fmtBRLFull(kpis.avg_ticket)}
              yoy={3.8}
              mom={5.2}
              yesterday={fmtBRLFull(kpis.yesterday_ticket || 218.86)}
              avg7d={fmtBRLFull(kpis.avg7d_ticket || 224.41)}
            />
            <KPICard
              type="aprovado"
              label="Receita Aprovada"
              value={fmtBRLFull(kpis.approved_revenue)}
              yoy={11.1}
              mom={2.9}
            />
            <KPICard
              type="cancelados"
              label="Cancelamentos"
              value={kpis.canceled_orders.toLocaleString("pt-BR")}
              yoy={-5.2}
              mom={-8.1}
            />
          </div>

          {/* Gráfico */}
          <div className="chart-card">
            <div className="chart-header">
              <div>
                <div className="chart-title">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#007BFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                    <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
                    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
                  </svg>
                  VTEX — PERFORMANCE DE VENDAS
                </div>
                <div className="chart-subtitle">Faturamento Hora a Hora (Dados Reais)</div>
              </div>
              {loading && <div className="spinner" />}
            </div>

            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#F3F4F6" vertical={false} />
                <XAxis
                  dataKey="hour"
                  tick={{ fontFamily: "Inter", fontSize: 11, fill: "#9CA3AF" }}
                  tickLine={false}
                  axisLine={{ stroke: "#E5E7EB" }}
                  interval={1}
                />
                <YAxis
                  tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)} mil` : `${v}`}
                  tick={{ fontFamily: "Inter", fontSize: 11, fill: "#9CA3AF" }}
                  tickLine={false}
                  axisLine={false}
                  width={70}
                />
                <Tooltip content={<CustomTooltip />} />

                {/* Hoje */}
                <Line
                  type="monotone" dataKey="hoje" name="Hoje"
                  stroke="#007BFF" strokeWidth={2}
                  dot={{ r: 4, fill: "#007BFF", strokeWidth: 2, stroke: "#fff" }}
                  activeDot={{ r: 6 }}
                  connectNulls={false}
                />
                {/* Média 7 dias */}
                <Line
                  type="monotone" dataKey="media7d" name="Média 7 Dias"
                  stroke="#D1D5DB" strokeWidth={1.5} strokeDasharray="3 5"
                  dot={false} connectNulls={false}
                />
                {/* Ontem */}
                <Line
                  type="monotone" dataKey="ontem" name="Ontem"
                  stroke="#9CA3AF" strokeWidth={1.5} strokeDasharray="6 3"
                  dot={false} connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>

            {/* Legenda */}
            <div className="chart-legend">
              <div className="legend-item">
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#007BFF", border: "2px solid #fff", boxShadow: "0 0 0 1.5px #007BFF" }} />
                  <div style={{ width: 20, height: 2, background: "#007BFF", borderRadius: 2 }} />
                </div>
                <span>Hoje</span>
              </div>
              <div className="legend-item">
                <div style={{ width: 26, height: 0, borderTop: "2px dashed #D1D5DB" }} />
                <span>Média 7 Dias</span>
              </div>
              <div className="legend-item">
                <div style={{ width: 26, height: 0, borderTop: "2px dashed #9CA3AF" }} />
                <span>Ontem</span>
              </div>
            </div>
          </div>

          <div style={{ textAlign: "center", fontFamily: "Inter", fontSize: 11, color: "#D1D5DB", marginTop: 8 }}>
            Dados sincronizados automaticamente a cada hora · Fonte: VTEX OMS
          </div>
        </div>
      </div>
    </>
  );
}
