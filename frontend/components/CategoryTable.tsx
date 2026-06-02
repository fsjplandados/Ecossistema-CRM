"use client";

import { useState, useMemo, useEffect } from "react";

interface CategoryData {
  category: string;
  revenue: number;
  qty_sold: number;
  avg_ticket: number;
  items_per_order: number;
  avg_price: number;
  revenue_yesterday: number;
  revenue_7d_avg: number;
  revenue_prev_month: number;
}

interface CategoryTableProps {
  data: CategoryData[];
  loading: boolean;
}

const fmtBRL = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export default function CategoryTable({ data, loading }: CategoryTableProps) {
  const [sortCol, setSortCol] = useState<keyof CategoryData | "growth">("revenue");
  const [sortDesc, setSortDesc] = useState(true);
  const [comparePeriod, setComparePeriod] = useState<"yesterday" | "7d" | "prev_month">("yesterday");

  const calcGrowth = (item: CategoryData) => {
    let prev = 0;
    if (comparePeriod === "yesterday") prev = item.revenue_yesterday;
    if (comparePeriod === "7d") prev = item.revenue_7d_avg;
    if (comparePeriod === "prev_month") prev = item.revenue_prev_month;
    
    if (prev === 0) return null;
    return ((item.revenue - prev) / prev) * 100;
  };

  const sortedData = useMemo(() => {
    const arr = [...data];
    arr.sort((a, b) => {
      let valA: any, valB: any;
      if (sortCol === "growth") {
        valA = calcGrowth(a) ?? -9999;
        valB = calcGrowth(b) ?? -9999;
      } else {
        valA = a[sortCol];
        valB = b[sortCol];
      }

      if (valA < valB) return sortDesc ? 1 : -1;
      if (valA > valB) return sortDesc ? -1 : 1;
      return 0;
    });
    return arr;
  }, [data, sortCol, sortDesc, comparePeriod]);

  const handleSort = (col: keyof CategoryData | "growth") => {
    if (sortCol === col) setSortDesc(!sortDesc);
    else {
      setSortCol(col);
      setSortDesc(true);
    }
  };

  const SortIcon = ({ col }: { col: string }) => {
    if (sortCol !== col) return <span className="sort-icon inactive">↕</span>;
    return <span className="sort-icon">{sortDesc ? "↓" : "↑"}</span>;
  };

  return (
    <div className="table-card">
      <div className="table-header">
        <h3 className="table-title">Performance por Categoria</h3>
        <div className="table-actions">
          <span style={{ fontSize: 12, color: "#6B7280" }}>Comparar com:</span>
          <select 
            className="filter-select" 
            style={{ minWidth: 100, padding: "4px 8px" }}
            value={comparePeriod}
            onChange={(e) => setComparePeriod(e.target.value as any)}
          >
            <option value="yesterday">Ontem</option>
            <option value="7d">Média 7 dias</option>
            <option value="prev_month">Mês anterior</option>
          </select>
        </div>
      </div>

      <div className="table-container">
        {loading ? (
          <div className="empty-state">
            <div className="spinner"></div>
            <span>Carregando categorias...</span>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th onClick={() => handleSort("category")}>Categoria <SortIcon col="category"/></th>
                <th onClick={() => handleSort("revenue")} style={{ textAlign: "right" }}>Faturamento <SortIcon col="revenue"/></th>
                <th onClick={() => handleSort("growth")} style={{ textAlign: "right" }}>Crescimento <SortIcon col="growth"/></th>
                <th onClick={() => handleSort("qty_sold")} style={{ textAlign: "right" }}>Vendidos <SortIcon col="qty_sold"/></th>
                <th onClick={() => handleSort("avg_ticket")} style={{ textAlign: "right" }}>Ticket Médio <SortIcon col="avg_ticket"/></th>
                <th onClick={() => handleSort("items_per_order")} style={{ textAlign: "right" }}>Itens/Pedido <SortIcon col="items_per_order"/></th>
                <th onClick={() => handleSort("avg_price")} style={{ textAlign: "right" }}>Preço Médio <SortIcon col="avg_price"/></th>
              </tr>
            </thead>
            <tbody>
              {sortedData.map((item, idx) => {
                const growth = calcGrowth(item);
                const isPositive = growth !== null && growth > 0;
                const isNegative = growth !== null && growth < 0;

                return (
                  <tr key={idx}>
                    <td className="font-medium">{item.category || "Sem categoria"}</td>
                    <td style={{ textAlign: "right" }}>{fmtBRL(item.revenue)}</td>
                    <td style={{ textAlign: "right" }}>
                      {growth === null ? (
                        <span style={{ color: "#9CA3AF" }}>-</span>
                      ) : (
                        <span className={isPositive ? "text-green" : isNegative ? "text-red" : ""}>
                          {isPositive ? "▲" : isNegative ? "▼" : ""} {Math.abs(growth).toFixed(2)}%
                        </span>
                      )}
                    </td>
                    <td style={{ textAlign: "right" }}>{item.qty_sold}</td>
                    <td style={{ textAlign: "right" }}>{fmtBRL(item.avg_ticket)}</td>
                    <td style={{ textAlign: "right" }}>{item.items_per_order.toFixed(2)}</td>
                    <td style={{ textAlign: "right" }}>{fmtBRL(item.avg_price)}</td>
                  </tr>
                );
              })}
              {sortedData.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "20px" }}>
                    Nenhum dado encontrado para os filtros selecionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
