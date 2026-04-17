"use client";

import { cn } from "@/lib/utils";
import { X, RotateCcw, Check } from "lucide-react";

// ── File type color map ─────────────────────────────────────

function getFileTypeColor(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    pdf: "#f87171",
    dwg: "#60a5fa",
    dxf: "#60a5fa",
    xls: "#34d399",
    xlsx: "#34d399",
    csv: "#34d399",
    rvt: "#22d3ee",
    xer: "#fbbf24",
    png: "#f472b6",
    jpg: "#f472b6",
    jpeg: "#f472b6",
    mp4: "#f472b6",
    zip: "#737a90",
    rar: "#737a90",
    pptx: "#fb923c",
    docx: "#60a5fa",
    doc: "#60a5fa",
  };
  return map[ext] ?? "#737a90";
}

function getFileIcon(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const icons: Record<string, string> = {
    pdf: "\u{1F4D5}",
    dwg: "\u{1F4D0}",
    dxf: "\u{1F4D0}",
    xls: "\u{1F4CA}",
    xlsx: "\u{1F4CA}",
    csv: "\u{1F4CA}",
    rvt: "\u{1F3D7}\uFE0F",
    xer: "\u{1F4C5}",
    png: "\u{1F5BC}\uFE0F",
    jpg: "\u{1F5BC}\uFE0F",
    jpeg: "\u{1F5BC}\uFE0F",
    mp4: "\u{1F3AC}",
    zip: "\u{1F4E6}",
    pptx: "\u{1F4CA}",
    docx: "\u{1F4C4}",
  };
  return icons[ext] ?? "\u{1F4C4}";
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`;
  return `${bytes} B`;
}

// ── Component ───────────────────────────────────────────────

interface QueuedFile {
  file: File;
  status: "queued" | "uploading" | "complete" | "failed";
}

interface UploadQueueProps {
  files: QueuedFile[];
  uploadProgress: Map<string, number>;
  onRemoveFile: (index: number) => void;
  onClearAll: () => void;
  onUploadAll: () => void;
  onRetry: (index: number) => void;
  isUploading: boolean;
  projectSelected: boolean;
}

export function UploadQueue({
  files,
  uploadProgress,
  onRemoveFile,
  onClearAll,
  onUploadAll,
  onRetry,
  isUploading,
  projectSelected,
}: UploadQueueProps) {
  if (files.length === 0) return null;

  const totalSize = files.reduce((sum, f) => sum + f.file.size, 0);

  return (
    <div className="mt-4 animate-slide-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium" style={{ color: "#cdd1dc" }}>
          {files.length} file{files.length !== 1 ? "s" : ""} ready to upload
          <span style={{ color: "#737a90" }}> · {formatFileSize(totalSize)}</span>
        </p>
        <button
          onClick={onClearAll}
          disabled={isUploading}
          className="text-xs font-medium px-2 py-1 rounded-md transition-all hover:bg-[#2a2f42]"
          style={{ color: "#737a90" }}
          aria-label="Clear all files"
        >
          Clear All
        </button>
      </div>

      {/* File list */}
      <div className="space-y-2 max-h-[240px] overflow-y-auto">
        {files.map((qf, i) => {
          const color = getFileTypeColor(qf.file.name);
          const icon = getFileIcon(qf.file.name);
          const progress = uploadProgress.get(qf.file.name) ?? 0;

          return (
            <div
              key={`${qf.file.name}-${i}`}
              className="flex items-center gap-3 px-3 py-2 rounded-lg border transition-all"
              style={{
                backgroundColor: "#1c2030",
                borderColor: "#2a2f42",
              }}
            >
              <span className="text-base" style={{ filter: `drop-shadow(0 0 4px ${color}40)` }}>
                {icon}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "#e8eaf0" }}>
                  {qf.file.name}
                </p>
                <p className="text-[11px]" style={{ color: "#737a90" }}>
                  {formatFileSize(qf.file.size)}
                </p>
                {qf.status === "uploading" && (
                  <div className="mt-1 h-1 rounded-full overflow-hidden" style={{ backgroundColor: "#2a2f42" }}>
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{
                        width: `${progress}%`,
                        backgroundColor: "#e8813a",
                      }}
                    />
                  </div>
                )}
              </div>

              {qf.status === "complete" && (
                <Check className="w-4 h-4 shrink-0" style={{ color: "#34d399" }} />
              )}
              {qf.status === "failed" && (
                <button
                  onClick={() => onRetry(i)}
                  className="p-1 rounded-md transition-all hover:bg-[#2a2f42]"
                  aria-label={`Retry uploading ${qf.file.name}`}
                >
                  <RotateCcw className="w-4 h-4" style={{ color: "#f87171" }} />
                </button>
              )}
              {(qf.status === "queued" || qf.status === "failed") && (
                <button
                  onClick={() => onRemoveFile(i)}
                  disabled={isUploading}
                  className="p-1 rounded-md transition-all hover:bg-[#2a2f42]"
                  style={{ color: "#737a90" }}
                  aria-label={`Remove ${qf.file.name}`}
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Upload All button */}
      {projectSelected && (
        <button
          onClick={onUploadAll}
          disabled={isUploading || files.every((f) => f.status === "complete")}
          className={cn(
            "w-full mt-4 py-3 rounded-xl text-sm font-semibold transition-all",
            isUploading || files.every((f) => f.status === "complete")
              ? "opacity-50 cursor-not-allowed"
              : "hover:brightness-110 shadow-lg"
          )}
          style={{
            backgroundColor: "#e8813a",
            color: "#161922",
            boxShadow: "0 4px 14px rgba(232, 129, 58, 0.25)",
          }}
          aria-label="Upload all files"
        >
          {isUploading ? "Uploading..." : "Upload All"}
        </button>
      )}
    </div>
  );
}
