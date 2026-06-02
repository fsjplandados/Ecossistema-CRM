"use client";

import { useState, useRef, useEffect } from "react";

interface MultiSelectFilterProps {
  label: string;
  options: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
  placeholder?: string;
}

export default function MultiSelectFilter({
  label,
  options,
  selected,
  onChange,
  placeholder = "Todos",
}: MultiSelectFilterProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // Fechar ao clicar fora
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const filtered = options.filter((o) =>
    o.toLowerCase().includes(search.toLowerCase())
  );

  const allSelected = options.length > 0 && selected.length === options.length;
  const noneSelected = selected.length === 0;

  const toggleAll = () => {
    onChange(allSelected ? [] : [...options]);
  };

  const toggle = (option: string) => {
    onChange(
      selected.includes(option)
        ? selected.filter((s) => s !== option)
        : [...selected, option]
    );
  };

  const displayText = noneSelected
    ? placeholder
    : allSelected
    ? "Todos"
    : selected.length === 1
    ? selected[0]
    : `${selected.length} selecionados`;

  return (
    <div className="filter-group" ref={ref} style={{ position: "relative" }}>
      <label className="filter-label">{label}</label>
      <button
        type="button"
        className="filter-select multi-select-trigger"
        onClick={() => setOpen(!open)}
      >
        <span className="multi-select-display">{displayText}</span>
        {selected.length > 0 && !allSelected && (
          <span className="multi-select-badge">{selected.length}</span>
        )}
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#9CA3AF"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            flexShrink: 0,
            transition: "transform 0.2s ease",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
          }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div className="multi-select-dropdown">
          {/* Busca */}
          <div className="multi-select-search-wrap">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#9CA3AF"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              className="multi-select-search"
              placeholder="Buscar..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
            {search && (
              <button
                type="button"
                className="multi-select-clear-search"
                onClick={() => setSearch("")}
              >
                ✕
              </button>
            )}
          </div>

          {/* Selecionar Todos */}
          <label className="multi-select-item multi-select-all">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleAll}
              className="multi-select-checkbox"
            />
            <span>Selecionar Todos</span>
          </label>

          <div className="multi-select-divider" />

          {/* Lista de opções */}
          <div className="multi-select-options">
            {filtered.length === 0 && (
              <div className="multi-select-empty">
                Nenhum resultado encontrado
              </div>
            )}
            {filtered.map((option) => (
              <label key={option} className="multi-select-item">
                <input
                  type="checkbox"
                  checked={selected.includes(option)}
                  onChange={() => toggle(option)}
                  className="multi-select-checkbox"
                />
                <span>{option}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
