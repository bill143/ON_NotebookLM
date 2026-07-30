"use client";

import type { VaultStats as VaultStatsType } from "@/types/vault";

// ── Component ───────────────────────────────────────────────

interface VaultStatsProps {
  stats: VaultStatsType;
}

export function VaultStats({ stats }: VaultStatsProps) {
  const metrics = [
    {
      icon: "\u{1F4C4}",
      label: "Processed Today",
      value: stats.documents_today,
      color: "#e8813a",
    },
    {
      icon: "\u26A1",
      label: "Workflows Triggered",
      value: stats.workflows_triggered,
      color: "#a78bfa",
    },
    {
      icon: "\u{1F441}\uFE0F",
      label: "Pending Reviews",
      value: stats.pending_reviews,
      color: stats.pending_reviews > 0 ? "#fbbf24" : "#737a90",
    },
    {
      icon: "\u2705",
      label: "Success Rate",
      value: `${stats.success_rate}%`,
      color: "#34d399",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="glass-card p-4 flex items-center gap-3"
        >
          <span className="text-xl" style={{ filter: `drop-shadow(0 0 6px ${m.color}40)` }}>
            {m.icon}
          </span>
          <div>
            <p className="text-lg font-bold" style={{ color: m.color }}>
              {m.value}
            </p>
            <p className="text-[11px] text-muted-foreground font-medium">{m.label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
