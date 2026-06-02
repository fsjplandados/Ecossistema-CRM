"use client";

import React from "react";

// ── Ícones SVG para cada tipo de KPI ────────────────────────
const kpiIcons: Record<string, { icon: React.ReactNode; color: string; bg: string; border: string }> = {
  receita: {
    border: "#EC4899",
    color: "#EC4899",
    bg: "#FDF2F8",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#EC4899" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
      </svg>
    ),
  },
  pedidos: {
    border: "#007BFF",
    color: "#007BFF",
    bg: "#EFF6FF",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#007BFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
        <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
      </svg>
    ),
  },
  ticket: {
    border: "#14B8A6",
    color: "#14B8A6",
    bg: "#F0FDFA",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#14B8A6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
        <line x1="7" y1="7" x2="7.01" y2="7"/>
      </svg>
    ),
  },
  aprovado: {
    border: "#10B981",
    color: "#10B981",
    bg: "#F0FDF4",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
    ),
  },
  cancelados: {
    border: "#EF4444",
    color: "#EF4444",
    bg: "#FEF2F2",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#EF4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
    ),
  },
};

// ── Seta indicadora ──────────────────────────────────────────
function Delta({ value, suffix = "%" }: { value: number | null; suffix?: string }) {
  if (value == null) return <span style={{ color: "#D1D5DB", fontSize: 11 }}>—</span>;
  const positive = value >= 0;
  const color = positive ? "#10B981" : "#EF4444";
  const arrow = positive ? "▲" : "▼";
  return (
    <span style={{ color, fontSize: 11, fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 2 }}>
      {arrow} {Math.abs(value).toFixed(1)}{suffix}
    </span>
  );
}

// ── Comparação período ──────────────────────────────────────
function PeriodRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
      <span style={{ fontFamily: "Inter", fontSize: 11, color: "#9CA3AF" }}>{label}</span>
      <span style={{ fontFamily: "Inter", fontSize: 11, fontWeight: 600, color: "#6B7280" }}>{value}</span>
    </div>
  );
}

// ── Props do KPI Card ────────────────────────────────────────
export interface KPICardProps {
  type: keyof typeof kpiIcons;
  label: string;
  value: string;
  yoy?: number | null;   // Year over Year %
  mom?: number | null;   // Month over Month %
  yesterday?: string;
  avg7d?: string;
}

export default function KPICard({
  type, label, value, yoy, mom, yesterday, avg7d
}: KPICardProps) {
  const cfg = kpiIcons[type] || kpiIcons.receita;

  return (
    <div
      className="kpi-card"
      style={{
        borderTop: `3px solid ${cfg.border}`,
        background: "#ffffff",
        borderRadius: "12px",
        padding: "18px 20px",
        border: "1px solid #E2E8F0",
        borderTopColor: cfg.border,
        boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
        transition: "transform 0.15s, box-shadow 0.15s",
        display: "flex",
        flexDirection: "column",
        gap: 0,
      }}
    >
      {/* Ícone + Label linha */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div
          style={{
            width: 40, height: 40, borderRadius: 10,
            background: cfg.bg,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {cfg.icon}
        </div>

        {/* Indicadores YoY / MoM */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
          {yoy != null && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontFamily: "Inter", fontSize: 10, color: "#9CA3AF" }}>YoY</span>
              <Delta value={yoy} />
            </div>
          )}
          {mom != null && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontFamily: "Inter", fontSize: 10, color: "#9CA3AF" }}>MoM</span>
              <Delta value={mom} />
            </div>
          )}
        </div>
      </div>

      {/* Label */}
      <div
        style={{
          fontFamily: "Montserrat, sans-serif",
          fontSize: 10,
          fontWeight: 600,
          color: "#9CA3AF",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          marginBottom: 4,
        }}
      >
        {label}
      </div>

      {/* Valor principal */}
      <div
        style={{
          fontFamily: "Montserrat, sans-serif",
          fontSize: 24,
          fontWeight: 700,
          color: "#111827",
          lineHeight: 1,
          marginBottom: 14,
        }}
      >
        {value}
      </div>

      {/* Comparações Hoje / Ontem / 7 Dias */}
      {(yesterday || avg7d) && (
        <div
          style={{
            borderTop: "1px solid #F3F4F6",
            paddingTop: 10,
            display: "flex",
            flexDirection: "column",
            gap: 3,
          }}
        >
          {yesterday && <PeriodRow label="Ontem" value={yesterday} />}
          {avg7d && <PeriodRow label="Média 7 dias" value={avg7d} />}
        </div>
      )}
    </div>
  );
}
