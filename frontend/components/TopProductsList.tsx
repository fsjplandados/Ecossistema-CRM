"use client";

import { useState } from "react";

interface TopProduct {
  product_id: string;
  name: string;
  image_url: string;
  revenue: number;
  qty_sold: number;
  participation_pct: number;
  revenue_yesterday: number;
}

interface TopProductsListProps {
  data: TopProduct[];
  loading: boolean;
  selectedHour: string | null;
  onClearHour: () => void;
}

const fmtBRL = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export default function TopProductsList({ data, loading, selectedHour, onClearHour }: TopProductsListProps) {
  const [sortBy, setSortBy] = useState<"revenue" | "qty">("revenue");

  const sortedData = [...data].sort((a, b) => {
    if (sortBy === "revenue") return b.revenue - a.revenue;
    return b.qty_sold - a.qty_sold;
  });

  return (
    <div className="table-card">
      <div className="table-header" style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
          <h3 className="table-title">
            Produtos mais vendidos
            {selectedHour && (
              <span style={{ color: "var(--blue-primary)", marginLeft: 6 }}>
                às {selectedHour}
              </span>
            )}
          </h3>
          <select 
            className="filter-select"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            style={{ minWidth: 120, padding: "4px 8px" }}
          >
            <option value="revenue">Faturamento</option>
            <option value="qty">Quantidade</option>
          </select>
        </div>
        {selectedHour && (
          <button onClick={onClearHour} style={{ fontSize: 11, background: 'none', border: 'none', color: '#EF4444', cursor: 'pointer', padding: 0 }}>
            ✖ Limpar filtro de hora
          </button>
        )}
      </div>

      <div className="product-list-container">
        {loading ? (
          <div className="empty-state">
            <div className="spinner"></div>
            <span>Carregando produtos...</span>
          </div>
        ) : sortedData.length === 0 ? (
          <div className="empty-state">Nenhum produto encontrado.</div>
        ) : (
          <div className="product-list">
            {sortedData.map((item, idx) => {
              const growth = item.revenue_yesterday > 0 
                ? ((item.revenue - item.revenue_yesterday) / item.revenue_yesterday) * 100 
                : null;
              
              const isPositive = growth !== null && growth > 0;
              const isNegative = growth !== null && growth < 0;

              return (
                <div key={idx} className="product-item">
                  <div className="product-image-wrap">
                    {item.image_url ? (
                      <img src={item.image_url} alt={item.name} className="product-image" />
                    ) : (
                      <div className="product-image-placeholder">🛒</div>
                    )}
                  </div>
                  <div className="product-info">
                    <div className="product-name" title={item.name}>{item.name}</div>
                    <div className="product-stats">
                      <span className="product-value">
                        {sortBy === "revenue" ? fmtBRL(item.revenue) : `${item.qty_sold} un`}
                      </span>
                      {growth !== null && (
                        <span className={`product-growth ${isPositive ? "text-green" : isNegative ? "text-red" : ""}`}>
                          {item.participation_pct.toFixed(2)}% {isPositive ? "▲" : isNegative ? "▼" : ""}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
