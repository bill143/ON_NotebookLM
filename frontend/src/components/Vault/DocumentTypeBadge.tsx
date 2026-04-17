"use client";

import { DocumentType } from "@/types/vault";

// ── Color map for document types ────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  [DocumentType.RFI]: "#60a5fa",
  [DocumentType.SUBMITTAL]: "#a78bfa",
  [DocumentType.SCHEDULE]: "#fbbf24",
  [DocumentType.INVOICE]: "#34d399",
  [DocumentType.CHANGE_ORDER]: "#f87171",
  [DocumentType.PERMIT]: "#fb923c",
  [DocumentType.COI]: "#22d3ee",
  [DocumentType.PLANS_DRAWINGS]: "#e8813a",
  [DocumentType.SPECIFICATIONS]: "#c084fc",
  [DocumentType.PHOTO_PROGRESS]: "#f472b6",
  [DocumentType.UNKNOWN]: "#737a90",
};

const DEFAULT_COLOR = "#60a5fa"; // info color

function getColor(type: DocumentType): string {
  return TYPE_COLORS[type] ?? DEFAULT_COLOR;
}

// ── Size variants ───────────────────────────────────────────

const SIZE_STYLES = {
  sm: { fontSize: "10px", padding: "4px 8px" },
  md: { fontSize: "11px", padding: "5px 10px" },
  lg: { fontSize: "13px", padding: "6px 14px" },
} as const;

// ── Component ───────────────────────────────────────────────

interface DocumentTypeBadgeProps {
  type: DocumentType;
  size?: "sm" | "md" | "lg";
}

export function DocumentTypeBadge({ type, size = "md" }: DocumentTypeBadgeProps) {
  const color = getColor(type);
  const sizeStyle = SIZE_STYLES[size];

  const label = type.replace(/_/g, " ");

  return (
    <span
      style={{
        backgroundColor: `${color}26`,
        color,
        fontSize: sizeStyle.fontSize,
        padding: sizeStyle.padding,
        borderRadius: "6px",
        fontWeight: 600,
        letterSpacing: "0.02em",
        whiteSpace: "nowrap",
        display: "inline-block",
        lineHeight: 1.2,
      }}
    >
      {label}
    </span>
  );
}
