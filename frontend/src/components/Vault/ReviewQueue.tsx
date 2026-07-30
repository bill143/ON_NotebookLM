"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { DocumentTypeBadge } from "./DocumentTypeBadge";
import { DocumentType, type VaultDocument } from "@/types/vault";
import { ChevronDown, Check } from "lucide-react";

// ── Document type options for override dropdown ─────────────

const DOC_TYPE_OPTIONS = Object.values(DocumentType).filter(
  (t) => t !== DocumentType.UNKNOWN
);

// ── Component ───────────────────────────────────────────────

interface ReviewQueueProps {
  items: VaultDocument[];
  onApprove: (documentId: string) => void;
  onReject: (documentId: string, overrideType: DocumentType) => void;
}

export function ReviewQueue({ items, onApprove, onReject }: ReviewQueueProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, DocumentType>>({});

  if (items.length === 0) return null;

  return (
    <div
      className="rounded-xl border transition-all animate-slide-in"
      style={{
        backgroundColor: "rgba(251, 191, 36, 0.06)",
        borderColor: "rgba(251, 191, 36, 0.2)",
      }}
    >
      {/* Banner header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        aria-expanded={!collapsed}
        aria-label={`${items.length} documents need review`}
      >
        <div className="flex items-center gap-2">
          <span className="text-base">{"\u{1F441}\uFE0F"}</span>
          <span className="text-sm font-semibold" style={{ color: "#fbbf24" }}>
            {items.length} document{items.length !== 1 ? "s" : ""} need your review
          </span>
        </div>
        <ChevronDown
          className={cn("w-4 h-4 transition-transform", !collapsed && "rotate-180")}
          style={{ color: "#fbbf24" }}
        />
      </button>

      {/* Review items */}
      {!collapsed && (
        <div className="px-4 pb-4 space-y-3">
          {items.map((doc) => {
            const selectedOverride = overrides[doc.id] ?? doc.document_type;

            return (
              <div
                key={doc.id}
                className="p-3 rounded-lg border"
                style={{
                  backgroundColor: "#1c2030",
                  borderColor: "#2a2f42",
                }}
              >
                {/* Filename */}
                <p className="text-sm font-medium mb-2" style={{ color: "#e8eaf0" }}>
                  {doc.filename}
                </p>

                {/* AI classification */}
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[11px]" style={{ color: "#737a90" }}>
                    AI classified as:
                  </span>
                  <DocumentTypeBadge type={doc.document_type} size="sm" />
                  <span
                    className="text-[10px] font-medium"
                    style={{
                      color:
                        doc.confidence_score >= 75
                          ? "#34d399"
                          : doc.confidence_score >= 50
                          ? "#fbbf24"
                          : "#f87171",
                    }}
                  >
                    {doc.confidence_score}%
                  </span>
                </div>

                {/* Why review needed */}
                <p className="text-[11px] mb-3" style={{ color: "#737a90" }}>
                  <span className="font-medium">Why review needed: </span>
                  {doc.confidence_score < 50
                    ? "Low confidence classification — AI is uncertain about document type."
                    : doc.confidence_score < 75
                    ? "Moderate confidence — multiple document types possible."
                    : "Flagged for human verification per project policy."}
                </p>

                {/* Override dropdown + actions */}
                <div className="flex items-center gap-2 flex-wrap">
                  <select
                    value={selectedOverride}
                    onChange={(e) =>
                      setOverrides((prev) => ({
                        ...prev,
                        [doc.id]: e.target.value as DocumentType,
                      }))
                    }
                    className="h-8 px-2 rounded-lg text-[11px] font-medium border"
                    style={{
                      backgroundColor: "#161922",
                      borderColor: "#2a2f42",
                      color: "#cdd1dc",
                    }}
                    aria-label={`Override document type for ${doc.filename}`}
                  >
                    {DOC_TYPE_OPTIONS.map((t) => (
                      <option key={t} value={t}>
                        {t.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>

                  <button
                    onClick={() => {
                      if (selectedOverride === doc.document_type) {
                        onApprove(doc.id);
                      } else {
                        onReject(doc.id, selectedOverride);
                      }
                    }}
                    className="flex items-center gap-1.5 h-8 px-3 rounded-lg text-[11px] font-semibold transition-all hover:brightness-110"
                    style={{
                      backgroundColor: "#34d399",
                      color: "#161922",
                    }}
                    aria-label={`Confirm classification for ${doc.filename}`}
                  >
                    <Check className="w-3 h-3" />
                    Confirm
                  </button>

                  <button
                    onClick={() => {
                      // Skip — just remove from local view
                      // Parent can handle this if needed
                    }}
                    className="text-[11px] font-medium px-2 transition-all hover:underline"
                    style={{ color: "#737a90" }}
                    aria-label={`Skip review for ${doc.filename}`}
                  >
                    Skip for now
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
