"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { truncate } from "@/lib/utils";
import { DocumentTypeBadge } from "./DocumentTypeBadge";
import { ProcessingStatus, type VaultDocument } from "@/types/vault";

// ── Processing step definitions ─────────────────────────────

const STEPS = [
  { key: ProcessingStatus.PENDING, label: "Uploading" },
  { key: ProcessingStatus.ANALYZING, label: "Analyzing" },
  { key: ProcessingStatus.CLASSIFIED, label: "Classified" },
  { key: ProcessingStatus.ROUTING, label: "Routing" },
  { key: ProcessingStatus.COMPLETE, label: "Complete" },
] as const;

const STATUS_ORDER: Record<string, number> = {
  [ProcessingStatus.PENDING]: 0,
  [ProcessingStatus.ANALYZING]: 1,
  [ProcessingStatus.CLASSIFIED]: 2,
  [ProcessingStatus.ROUTING]: 3,
  [ProcessingStatus.COMPLETE]: 4,
  [ProcessingStatus.FAILED]: -1,
  [ProcessingStatus.NEEDS_REVIEW]: 2,
};

function getStepState(
  stepKey: ProcessingStatus,
  docStatus: ProcessingStatus
): "completed" | "active" | "pending" {
  const stepIdx = STATUS_ORDER[stepKey] ?? 0;
  const docIdx = STATUS_ORDER[docStatus] ?? 0;

  if (docStatus === ProcessingStatus.FAILED) return stepIdx === 0 ? "completed" : "pending";
  if (docStatus === ProcessingStatus.NEEDS_REVIEW) {
    if (stepIdx < 2) return "completed";
    if (stepIdx === 2) return "active";
    return "pending";
  }
  if (stepIdx < docIdx) return "completed";
  if (stepIdx === docIdx) return "active";
  return "pending";
}

// ── Confidence bar color ────────────────────────────────────

function getConfidenceColor(score: number): string {
  if (score >= 75) return "#34d399";
  if (score >= 50) return "#fbbf24";
  return "#f87171";
}

// ── Component ───────────────────────────────────────────────

interface LibrarianStatusProps {
  documents: VaultDocument[];
}

export function LibrarianStatus({ documents }: LibrarianStatusProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [documents.length]);

  const activeCount = documents.filter(
    (d) =>
      d.processing_status !== ProcessingStatus.COMPLETE &&
      d.processing_status !== ProcessingStatus.FAILED
  ).length;

  const completedCount = documents.filter(
    (d) => d.processing_status === ProcessingStatus.COMPLETE
  ).length;

  return (
    <div className="glass-card p-4 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <span className={cn("text-lg", activeCount > 0 && "animate-pulse")}>
          {"\u{1F9E0}"}
        </span>
        <h3 className="text-sm font-semibold" style={{ color: "#e8eaf0" }}>
          {activeCount > 0 ? "The Librarian is working..." : "The Librarian"}
        </h3>
        {activeCount > 0 && (
          <div
            className="w-2 h-2 rounded-full animate-pulse ml-auto"
            style={{ backgroundColor: "#e8813a" }}
          />
        )}
      </div>

      {/* Document cards or empty state */}
      {documents.length === 0 ? (
        <div className="flex-1 flex items-center justify-center py-8">
          <p className="text-sm text-center" style={{ color: "#737a90" }}>
            Upload documents above to begin
          </p>
        </div>
      ) : (
        <div ref={scrollRef} className="space-y-3 max-h-[400px] overflow-y-auto">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="p-3 rounded-lg border transition-all"
              style={{
                backgroundColor: "#1c2030",
                borderColor: "#2a2f42",
              }}
            >
              {/* File name */}
              <p className="text-sm font-medium mb-2" style={{ color: "#e8eaf0" }}>
                {truncate(doc.filename, 40)}
              </p>

              {/* Status steps */}
              <div className="flex items-center gap-1 mb-2">
                {STEPS.map((step, i) => {
                  const state = getStepState(step.key, doc.processing_status);
                  return (
                    <div key={step.key} className="flex items-center gap-1">
                      <div className="flex flex-col items-center">
                        <div
                          className={cn(
                            "w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold transition-all",
                            state === "completed" && "bg-[#34d399]/20",
                            state === "active" && "bg-[#e8813a]/20 animate-pulse",
                            state === "pending" && "bg-[#2a2f42]"
                          )}
                          style={{
                            color:
                              state === "completed"
                                ? "#34d399"
                                : state === "active"
                                ? "#e8813a"
                                : "#737a90",
                          }}
                        >
                          {state === "completed" ? "\u2713" : i + 1}
                        </div>
                        <span
                          className="text-[8px] mt-0.5 font-medium"
                          style={{
                            color:
                              state === "completed"
                                ? "#34d399"
                                : state === "active"
                                ? "#e8813a"
                                : "#737a90",
                          }}
                        >
                          {step.label}
                        </span>
                      </div>
                      {i < STEPS.length - 1 && (
                        <div
                          className="w-4 h-px mb-3"
                          style={{
                            backgroundColor:
                              state === "completed" ? "#34d399" : "#2a2f42",
                          }}
                        />
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Document type badge — after classified */}
              {STATUS_ORDER[doc.processing_status] >= 2 && (
                <div className="flex items-center gap-2 mb-2">
                  <DocumentTypeBadge type={doc.document_type} size="sm" />
                  {doc.requires_human_review && (
                    <span
                      className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        backgroundColor: "rgba(251, 191, 36, 0.15)",
                        color: "#fbbf24",
                      }}
                    >
                      Needs Review
                    </span>
                  )}
                </div>
              )}

              {/* Confidence bar */}
              {doc.confidence_score > 0 && (
                <div className="mb-2">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[10px]" style={{ color: "#737a90" }}>
                      Confidence
                    </span>
                    <span
                      className="text-[10px] font-semibold"
                      style={{ color: getConfidenceColor(doc.confidence_score) }}
                    >
                      {doc.confidence_score}%
                    </span>
                  </div>
                  <div
                    className="h-1 rounded-full overflow-hidden"
                    style={{ backgroundColor: "#2a2f42" }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${doc.confidence_score}%`,
                        backgroundColor: getConfidenceColor(doc.confidence_score),
                      }}
                    />
                  </div>
                </div>
              )}

              {/* Workflow actions after complete */}
              {doc.processing_status === ProcessingStatus.COMPLETE &&
                doc.librarian_decision?.workflow_triggers &&
                doc.librarian_decision.workflow_triggers.length > 0 && (
                  <div className="mt-2 pt-2 border-t" style={{ borderColor: "#2a2f42" }}>
                    {doc.librarian_decision.workflow_triggers.map((action, j) => (
                      <p
                        key={j}
                        className="text-[10px] leading-relaxed"
                        style={{ color: "#737a90" }}
                      >
                        {"\u2713"} {action}
                      </p>
                    ))}
                  </div>
                )}

              {/* Failed state */}
              {doc.processing_status === ProcessingStatus.FAILED && (
                <p
                  className="text-[11px] font-medium mt-1"
                  style={{ color: "#f87171" }}
                >
                  Processing failed — will retry automatically
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Overall progress */}
      {documents.length > 0 && (
        <div className="mt-3 pt-3 border-t" style={{ borderColor: "#2a2f42" }}>
          <p className="text-[11px] font-medium" style={{ color: "#737a90" }}>
            {completedCount} of {documents.length} documents complete
          </p>
        </div>
      )}
    </div>
  );
}
