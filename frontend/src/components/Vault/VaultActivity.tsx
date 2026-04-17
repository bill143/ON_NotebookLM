"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";
import { DocumentTypeBadge } from "./DocumentTypeBadge";
import { ProcessingStatus, DocumentType, type VaultActivityItem } from "@/types/vault";
import { ChevronDown } from "lucide-react";

// ── Filter types ────────────────────────────────────────────

type FilterKey = "all" | "needs_review" | "rfi" | "submittal" | "invoice" | "other";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Needs Review" },
  { key: "rfi", label: "RFI" },
  { key: "submittal", label: "Submittal" },
  { key: "invoice", label: "Invoice" },
  { key: "other", label: "Other" },
];

function getStatusChip(status: ProcessingStatus): { label: string; color: string } {
  switch (status) {
    case ProcessingStatus.COMPLETE:
      return { label: "Complete", color: "#34d399" };
    case ProcessingStatus.NEEDS_REVIEW:
      return { label: "Needs Review", color: "#fbbf24" };
    case ProcessingStatus.FAILED:
      return { label: "Failed", color: "#f87171" };
    default:
      return { label: "Processing", color: "#60a5fa" };
  }
}

// ── Component ───────────────────────────────────────────────

interface VaultActivityProps {
  activities: VaultActivityItem[];
}

export function VaultActivity({ activities }: VaultActivityProps) {
  const [filter, setFilter] = useState<FilterKey>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = activities.filter((a) => {
    switch (filter) {
      case "needs_review":
        return a.processing_status === ProcessingStatus.NEEDS_REVIEW;
      case "rfi":
        return a.document_type === DocumentType.RFI;
      case "submittal":
        return a.document_type === DocumentType.SUBMITTAL;
      case "invoice":
        return a.document_type === DocumentType.INVOICE;
      case "other":
        return (
          a.document_type !== DocumentType.RFI &&
          a.document_type !== DocumentType.SUBMITTAL &&
          a.document_type !== DocumentType.INVOICE
        );
      default:
        return true;
    }
  }).slice(0, 50);

  return (
    <div className="glass-card p-4 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold" style={{ color: "#e8eaf0" }}>
          Recent Activity
        </h3>
      </div>

      {/* Filter pills */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={cn(
              "text-[11px] font-medium px-2.5 py-1 rounded-lg transition-all",
              filter === f.key
                ? "text-[#161922]"
                : "hover:bg-[#2a2f42]"
            )}
            style={
              filter === f.key
                ? { backgroundColor: "#e8813a", color: "#161922" }
                : { color: "#737a90" }
            }
            aria-label={`Filter by ${f.label}`}
            aria-pressed={filter === f.key}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Activity list */}
      {filtered.length === 0 ? (
        <div className="flex-1 flex items-center justify-center py-8">
          <p className="text-sm text-center" style={{ color: "#737a90" }}>
            {activities.length === 0
              ? "No documents processed yet. Upload your first batch above."
              : "No matching activities."}
          </p>
        </div>
      ) : (
        <div className="space-y-0 max-h-[400px] overflow-y-auto">
          {filtered.map((item) => {
            const statusChip = getStatusChip(item.processing_status);
            const expanded = expandedId === item.id;

            return (
              <div key={item.id}>
                <button
                  onClick={() => setExpandedId(expanded ? null : item.id)}
                  className="w-full flex items-center gap-3 px-2 py-2.5 text-left transition-all hover:bg-[#1c2030] rounded-lg"
                  aria-expanded={expanded}
                  aria-label={`Activity: ${item.filename}`}
                >
                  {/* Badge */}
                  <DocumentTypeBadge type={item.document_type} size="sm" />

                  {/* Details */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: "#e8eaf0" }}>
                      {item.filename}
                    </p>
                    <p className="text-[11px]" style={{ color: "#737a90" }}>
                      {item.project_name} &middot; {formatRelativeTime(item.created_at)}
                    </p>
                  </div>

                  {/* Status + expand */}
                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        backgroundColor: `${statusChip.color}20`,
                        color: statusChip.color,
                      }}
                    >
                      {statusChip.label}
                    </span>
                    <ChevronDown
                      className={cn(
                        "w-3 h-3 transition-transform",
                        expanded && "rotate-180"
                      )}
                      style={{ color: "#737a90" }}
                    />
                  </div>
                </button>

                {/* Expanded details */}
                {expanded && item.librarian_decision && (
                  <div
                    className="mx-2 mb-2 p-3 rounded-lg animate-slide-in"
                    style={{
                      backgroundColor: "#1c2030",
                      borderLeft: "2px solid #e8813a",
                    }}
                  >
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div>
                        <span style={{ color: "#737a90" }}>Type: </span>
                        <DocumentTypeBadge type={item.librarian_decision.document_type} size="sm" />
                      </div>
                      <div>
                        <span style={{ color: "#737a90" }}>Confidence: </span>
                        <span style={{ color: "#e8eaf0" }}>
                          {item.librarian_decision.confidence_score}%
                        </span>
                      </div>
                      <div className="col-span-2">
                        <span style={{ color: "#737a90" }}>Routing: </span>
                        <span style={{ color: "#e8eaf0" }}>
                          {item.librarian_decision.routing_instructions}
                        </span>
                      </div>
                      {item.librarian_decision.workflow_triggers.length > 0 && (
                        <div className="col-span-2">
                          <span style={{ color: "#737a90" }}>Actions: </span>
                          <span style={{ color: "#cdd1dc" }}>
                            {item.librarian_decision.workflow_triggers.join(" · ")}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Divider */}
                <div className="h-px mx-2" style={{ backgroundColor: "#2a2f42" }} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
