"use client";

import { useState, useMemo } from "react";

interface CategoryData {
  category: string;
  revenue: number;
  qty_sold: number;
  total_orders: number;
  avg_ticket: number;
  items_per_order: number;
  avg_price: number;
  
  yd_revenue: number;
  yd_qty: number;
  yd_orders: number;
  yd_avg_ticket: number;
  yd_items_per_order: number;
  yd_avg_price: number;

  a7_revenue: number;
  a7_qty: number;
  a7_orders: number;
  a7_avg_ticket: number;
  a7_items_per_order: number;
  a7_avg_price: number;

  pm_revenue: number;
  pm_qty: number;
  pm_orders: number;
  pm_avg_ticket: number;
  pm_items_per_order: number;
  pm_avg_price: number;
}

interface CategoryTableProps {
  data: CategoryData[];
  loading: boolean;
  onSelectCategory?: (category: string) => void;
}

const fmtBRL = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fmtNum = (v: number) =>
  v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });

export default function CategoryTable({ data, loading, onSelectCategory }: CategoryTableProps) {
  const [sortCol, setSortCol] = useState<keyof CategoryData>("revenue");
  const [sortDesc, setSortDesc] = useState(true);
  const [comparePeriod, setComparePeriod] = useState<"yesterday" | "7d" | "prev_month">("yesterday");

  const calcGrowth = (current: number, item: CategoryData, metric: string) => {
    let prev = 0;
    if (comparePeriod === "yesterday") prev = (item as any)[`yd_${metric}`];
    if (comparePeriod === "7d") prev = (item as any)[`a7_${metric}`];
    if (comparePeriod === "prev_month") prev = (item as any)[`pm_${metric}`];
    
    if (!prev || prev === 0) return null;
    return ((current - prev) / prev) * 100;
  };

  const sortedData = useMemo(() => {
    const arr = [...data];
    arr.sort((a, b) => {
      const valA = a[sortCol];
      const valB = b[sortCol];

      if (valA < valB) return sortDesc ? 1 : -1;
      if (valA > valB) return sortDesc ? -1 : 1;
      return 0;
    });
    return arr;
  }, [data, sortCol, sortDesc]);

  const handleSort = (col: keyof CategoryData) => {
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

  const renderCell = (current: number, item: CategoryData, metric: string, isMoney = false) => {
    const growth = calcGrowth(current, item, metric);
    const isPositive = growth !== null && growth > 0;
    const isNegative = growth !== null && growth < 0;

    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
        <span style={{ fontWeight: 600, color: "#111827", fontSize: 13 }}>
          {isMoney ? fmtBRL(current) : fmtNum(current)}
        </span>
        {growth === null ? (
          <span style={{ fontSize: 11, color: "#9CA3AF" }}>-</span>
        ) : (
          <span className={isPositive ? "text-green" : isNegative ? "text-red" : ""} style={{ fontSize: 11, marginTop: 2 }}>
            {isPositive ? "▲" : isNegative ? "▼" : ""} {Math.abs(growth).toFixed(2)}%
          </span>
        )}
      </div>
    );
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

      <div className="table-container vtex-style-table">
        {loading ? (
          <div className="empty-state">
            <div className="spinner"></div>
            <span>Carregando categorias...</span>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th onClick={() => handleSort("category")} style={{ textAlign: "left" }}>Categoria <SortIcon col="category"/></th>
                <th onClick={() => handleSort("revenue")} style={{ textAlign: "right" }}>Receita (captada) <SortIcon col="revenue"/></th>
                <th onClick={() => handleSort("total_orders")} style={{ textAlign: "right" }}>Pedidos (captados) <SortIcon col="total_orders"/></th>
                <th onClick={() => handleSort("avg_ticket")} style={{ textAlign: "right" }}>Ticket médio (captado) <SortIcon col="avg_ticket"/></th>
                <th onClick={() => handleSort("items_per_order")} style={{ textAlign: "right" }}>Itens por pedido <SortIcon col="items_per_order"/></th>
                <th onClick={() => handleSort("avg_price")} style={{ textAlign: "right" }}>Preço médio por item <SortIcon col="avg_price"/></th>
              </tr>
            </thead>
            <tbody>
              {/* Calcula a linha Total */}
              {sortedData.length > 0 && (() => {
                const totalRevenue = sortedData.reduce((acc, item) => acc + item.revenue, 0);
                const totalOrders = sortedData.reduce((acc, item) => acc + item.total_orders, 0);
                const totalQty = sortedData.reduce((acc, item) => acc + item.qty_sold, 0);
                const totalAvgTicket = totalOrders > 0 ? totalRevenue / totalOrders : 0;
                const totalItemsPerOrder = totalOrders > 0 ? totalQty / totalOrders : 0;
                const totalAvgPrice = totalQty > 0 ? totalRevenue / totalQty : 0;

                const totalItem: any = {
                  yd_revenue: sortedData.reduce((acc, item) => acc + item.yd_revenue, 0),
                  yd_orders: sortedData.reduce((acc, item) => acc + item.yd_orders, 0),
                  yd_qty: sortedData.reduce((acc, item) => acc + item.yd_qty, 0),
                  
                  a7_revenue: sortedData.reduce((acc, item) => acc + item.a7_revenue, 0),
                  a7_orders: sortedData.reduce((acc, item) => acc + item.a7_orders, 0),
                  a7_qty: sortedData.reduce((acc, item) => acc + item.a7_qty, 0),
                  
                  pm_revenue: sortedData.reduce((acc, item) => acc + item.pm_revenue, 0),
                  pm_orders: sortedData.reduce((acc, item) => acc + item.pm_orders, 0),
                  pm_qty: sortedData.reduce((acc, item) => acc + item.pm_qty, 0),
                };

                // Calcular as medias do passado pra calcular o crescimento total
                ["yd", "a7", "pm"].forEach(p => {
                  totalItem[`${p}_avg_ticket`] = totalItem[`${p}_orders`] > 0 ? totalItem[`${p}_revenue`] / totalItem[`${p}_orders`] : 0;
                  totalItem[`${p}_items_per_order`] = totalItem[`${p}_orders`] > 0 ? totalItem[`${p}_qty`] / totalItem[`${p}_orders`] : 0;
                  totalItem[`${p}_avg_price`] = totalItem[`${p}_qty`] > 0 ? totalItem[`${p}_revenue`] / totalItem[`${p}_qty`] : 0;
                });

                return (
                  <tr className="total-row">
                    <td className="font-medium" style={{ fontSize: 14 }}>Total</td>
                    <td>{renderCell(totalRevenue, totalItem, "revenue", true)}</td>
                    <td>{renderCell(totalOrders, totalItem, "orders")}</td>
                    <td>{renderCell(totalAvgTicket, totalItem, "avg_ticket", true)}</td>
                    <td>{renderCell(totalItemsPerOrder, totalItem, "items_per_order")}</td>
                    <td>{renderCell(totalAvgPrice, totalItem, "avg_price", true)}</td>
                  </tr>
                );
              })()}

              {sortedData.map((item, idx) => (
                <tr 
                  key={idx} 
                  onClick={() => onSelectCategory && onSelectCategory(item.category)}
                  style={{ cursor: onSelectCategory ? "pointer" : "default" }}
                  className="interactive-row"
                >
                  <td className="font-medium" style={{ color: "#3B82F6" }}>
                    {idx + 1}. {item.category || "Sem categoria"}
                  </td>
                  <td>{renderCell(item.revenue, item, "revenue", true)}</td>
                  <td>{renderCell(item.total_orders, item, "orders")}</td>
                  <td>{renderCell(item.avg_ticket, item, "avg_ticket", true)}</td>
                  <td>{renderCell(item.items_per_order, item, "items_per_order")}</td>
                  <td>{renderCell(item.avg_price, item, "avg_price", true)}</td>
                </tr>
              ))}
              
              {sortedData.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "20px" }}>
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
