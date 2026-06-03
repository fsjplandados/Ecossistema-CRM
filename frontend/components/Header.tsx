"use client";

import { useEffect, useState } from "react";
import Image from "next/image";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Header() {
  const [lastSync, setLastSync] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/sync/status`)
      .then((r) => r.json())
      .then((data) => {
        if (data.last_sync) {
          const date = new Date(data.last_sync);
          setLastSync(
            date.toLocaleString("pt-BR", {
              day: "2-digit", month: "2-digit",
              hour: "2-digit", minute: "2-digit",
            })
          );
        }
      })
      .catch(() => {});
  }, []);

  return (
    <header className="header">
      {/* Logo + Título */}
      <div className="header-logo">
        <Image
          src="/logo.png"
          alt="Farmácias São João"
          width={160}
          height={50}
          priority
          style={{ objectFit: "contain", height: 46, width: "auto" }}
        />
        <div style={{ borderLeft: "1px solid rgba(255,255,255,0.25)", paddingLeft: 16, marginLeft: 4 }}>
          <div className="header-title">Eco CRM</div>
          <div className="header-subtitle">Analytics & Inteligência</div>
        </div>
      </div>

      {/* Right side */}
      <div className="header-right">
        {/* Badge VTEX */}
        <div style={{
          background: "rgba(255,255,255,0.12)",
          border: "1px solid rgba(255,255,255,0.2)",
          borderRadius: 20,
          padding: "4px 14px",
          fontFamily: "Montserrat, sans-serif",
          fontSize: 11,
          fontWeight: 700,
          color: "rgba(255,255,255,0.9)",
          letterSpacing: "0.05em",
          textTransform: "uppercase" as const,
        }}>
          VTEX · Live
        </div>

        {/* Última sincronização */}
        {lastSync && (
          <div className="sync-badge">
            <span className="sync-dot" />
            Sync {lastSync}
          </div>
        )}

        {/* Avatar */}
        <div style={{
          width: 36, height: 36, borderRadius: "50%",
          background: "rgba(255,255,255,0.2)",
          border: "2px solid rgba(255,255,255,0.3)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: "Montserrat, sans-serif", fontSize: 13, fontWeight: 700,
          color: "#fff",
        }}>
          SJ
        </div>
      </div>
    </header>
  );
}
