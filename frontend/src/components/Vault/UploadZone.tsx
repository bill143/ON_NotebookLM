"use client";

import { useState, useRef, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Upload } from "lucide-react";
import { UploadQueue } from "./UploadQueue";

// ── Accepted format pills ───────────────────────────────────

const FORMAT_PILLS = [
  "PDF", "DWG", "XLS", "RVT", "XER", "PNG", "JPG", "MP4", "ZIP", "PPTX", "DOCX", "+ MORE",
];

// ── Types ───────────────────────────────────────────────────

interface QueuedFile {
  file: File;
  status: "queued" | "uploading" | "complete" | "failed";
}

interface UploadZoneProps {
  projectSelected: boolean;
  isUploading: boolean;
  uploadProgress: Map<string, number>;
  onUpload: (files: File[]) => void;
}

// ── Component ───────────────────────────────────────────────

export function UploadZone({
  projectSelected,
  isUploading,
  uploadProgress,
  onUpload,
}: UploadZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [queuedFiles, setQueuedFiles] = useState<QueuedFile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((fileList: FileList | null) => {
    if (!fileList?.length) return;
    const newFiles: QueuedFile[] = Array.from(fileList).map((f) => ({
      file: f,
      status: "queued" as const,
    }));
    setQueuedFiles((prev) => [...prev, ...newFiles]);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      if (!projectSelected) return;
      addFiles(e.dataTransfer.files);
    },
    [projectSelected, addFiles]
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (projectSelected) setDragging(true);
    },
    [projectSelected]
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
  }, []);

  const handleBrowse = useCallback(() => {
    if (!projectSelected) return;
    fileInputRef.current?.click();
  }, [projectSelected]);

  const handleUploadAll = useCallback(() => {
    const filesToUpload = queuedFiles
      .filter((f) => f.status === "queued" || f.status === "failed")
      .map((f) => f.file);
    if (filesToUpload.length === 0) return;

    setQueuedFiles((prev) =>
      prev.map((f) =>
        f.status === "queued" || f.status === "failed" ? { ...f, status: "uploading" as const } : f
      )
    );

    onUpload(filesToUpload);

    // Mark complete after a short delay (real progress comes from hook)
    setTimeout(() => {
      setQueuedFiles((prev) =>
        prev.map((f) => (f.status === "uploading" ? { ...f, status: "complete" as const } : f))
      );
    }, 2000);
  }, [queuedFiles, onUpload]);

  const handleRemoveFile = useCallback((index: number) => {
    setQueuedFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleClearAll = useCallback(() => {
    setQueuedFiles([]);
  }, []);

  const handleRetry = useCallback((index: number) => {
    setQueuedFiles((prev) =>
      prev.map((f, i) => (i === index ? { ...f, status: "queued" as const } : f))
    );
  }, []);

  const disabled = !projectSelected;

  return (
    <div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = "";
        }}
        aria-label="Select files to upload"
      />

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleBrowse}
        className={cn(
          "relative rounded-2xl border-2 border-dashed transition-all cursor-pointer",
          "flex flex-col items-center justify-center text-center",
          "min-h-[300px] px-6 py-10",
          disabled && "opacity-40 cursor-not-allowed",
          dragging
            ? "border-[#e8813a] bg-[#e8813a]/5 shadow-[0_0_40px_rgba(232,129,58,0.15)]"
            : "border-[#2a2f42] hover:border-[#e8813a]/40 bg-[#1c2030]/50"
        )}
        role="button"
        tabIndex={0}
        aria-label={disabled ? "Select a project first" : "Drop files here or click to browse"}
        aria-disabled={disabled}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleBrowse();
          }
        }}
      >
        {/* Upload icon */}
        <div
          className={cn(
            "w-16 h-16 rounded-2xl flex items-center justify-center mb-4 transition-all",
            dragging ? "scale-110" : ""
          )}
          style={{
            backgroundColor: "rgba(232, 129, 58, 0.1)",
          }}
        >
          <Upload
            className="w-8 h-8 transition-all"
            style={{ color: "#e8813a" }}
          />
        </div>

        {/* Text */}
        <h3
          className="text-lg font-semibold mb-1"
          style={{ color: "#e8eaf0" }}
        >
          Drop all your documents here
        </h3>
        <p className="text-sm mb-5" style={{ color: "#737a90" }}>
          Any format &middot; Any quantity &middot; AI takes care of the rest
        </p>

        {/* Format pills */}
        <div className="flex flex-wrap gap-1.5 justify-center mb-5">
          {FORMAT_PILLS.map((fmt) => (
            <span
              key={fmt}
              className="text-[10px] font-semibold px-2 py-1 rounded-md"
              style={{
                backgroundColor: "#2a2f42",
                color: "#737a90",
              }}
            >
              {fmt}
            </span>
          ))}
        </div>

        {/* Browse button */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            handleBrowse();
          }}
          disabled={disabled}
          className={cn(
            "px-5 py-2.5 rounded-xl text-sm font-semibold transition-all",
            disabled
              ? "opacity-50 cursor-not-allowed"
              : "hover:brightness-110 shadow-lg"
          )}
          style={{
            backgroundColor: "#e8813a",
            color: "#161922",
            boxShadow: disabled ? "none" : "0 4px 14px rgba(232, 129, 58, 0.25)",
          }}
          aria-label="Browse files"
        >
          Browse Files
        </button>

        {disabled && (
          <p className="text-xs mt-3" style={{ color: "#737a90" }}>
            Select a project first
          </p>
        )}
      </div>

      {/* File queue */}
      <UploadQueue
        files={queuedFiles}
        uploadProgress={uploadProgress}
        onRemoveFile={handleRemoveFile}
        onClearAll={handleClearAll}
        onUploadAll={handleUploadAll}
        onRetry={handleRetry}
        isUploading={isUploading}
        projectSelected={projectSelected}
      />
    </div>
  );
}
