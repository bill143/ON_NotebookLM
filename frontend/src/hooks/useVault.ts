"use client";

import { useState, useCallback, useRef } from "react";
import {
  type VaultDocument,
  type VaultUploadResponse,
  type VaultActivityItem,
  type VaultStats,
  ProcessingStatus,
  DocumentType,
} from "@/types/vault";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── useVault Hook ───────────────────────────────────────────

export function useVault() {
  const [uploadProgress, setUploadProgress] = useState<Map<string, number>>(new Map());
  const [processingDocuments, setProcessingDocuments] = useState<VaultDocument[]>([]);
  const [reviewQueue, setReviewQueue] = useState<VaultDocument[]>([]);
  const [recentActivity, setRecentActivity] = useState<VaultActivityItem[]>([]);
  const [stats, setStats] = useState<VaultStats>({
    documents_today: 0,
    workflows_triggered: 0,
    pending_reviews: 0,
    success_rate: 100,
  });
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  // ── Upload Documents ────────────────────────────────────

  const uploadDocuments = useCallback(
    async (files: File[], projectId: string) => {
      setIsUploading(true);
      setError(null);

      const progressMap = new Map<string, number>();
      files.forEach((f) => progressMap.set(f.name, 0));
      setUploadProgress(new Map(progressMap));

      try {
        const formData = new FormData();
        formData.append("project_id", projectId);
        files.forEach((file) => formData.append("files", file));

        const xhr = new XMLHttpRequest();

        const uploadPromise = new Promise<VaultUploadResponse>((resolve, reject) => {
          xhr.upload.addEventListener("progress", (e) => {
            if (e.lengthComputable) {
              const pct = Math.round((e.loaded / e.total) * 100);
              const updated = new Map<string, number>();
              files.forEach((f) => updated.set(f.name, pct));
              setUploadProgress(new Map(updated));
            }
          });

          xhr.addEventListener("load", () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve(JSON.parse(xhr.responseText) as VaultUploadResponse);
            } else {
              reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
            }
          });

          xhr.addEventListener("error", () => reject(new Error("Network error during upload")));
          xhr.addEventListener("abort", () => reject(new Error("Upload aborted")));

          xhr.open("POST", `${API_BASE}/api/v1/vault/upload`);
          xhr.send(formData);
        });

        const response = await uploadPromise;

        // Mark all files as complete
        const doneMap = new Map<string, number>();
        files.forEach((f) => doneMap.set(f.name, 100));
        setUploadProgress(new Map(doneMap));

        // Start polling for each uploaded document
        for (const docId of response.document_ids) {
          pollStatus(docId);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setIsUploading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  // ── Poll Status ─────────────────────────────────────────

  const pollStatus = useCallback((documentId: string) => {
    // Clear existing timer if any
    const existing = pollTimers.current.get(documentId);
    if (existing) clearInterval(existing);

    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/vault/status/${documentId}`);
        if (!res.ok) return;

        const doc: VaultDocument = await res.json();

        setProcessingDocuments((prev) => {
          const idx = prev.findIndex((d) => d.id === doc.id);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = doc;
            return updated;
          }
          return [...prev, doc];
        });

        if (
          doc.processing_status === ProcessingStatus.COMPLETE ||
          doc.processing_status === ProcessingStatus.FAILED
        ) {
          const t = pollTimers.current.get(documentId);
          if (t) clearInterval(t);
          pollTimers.current.delete(documentId);

          if (doc.requires_human_review) {
            setReviewQueue((prev) =>
              prev.some((d) => d.id === doc.id) ? prev : [...prev, doc]
            );
          }
        }
      } catch {
        // Silently retry on next interval
      }
    }, 3000);

    pollTimers.current.set(documentId, timer);
  }, []);

  // ── Get Queue ───────────────────────────────────────────

  const getQueue = useCallback(async (projectId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/vault/queue/${projectId}`);
      if (!res.ok) throw new Error("Failed to fetch queue");
      const data: VaultDocument[] = await res.json();
      setReviewQueue(data.filter((d) => d.requires_human_review));
      setProcessingDocuments(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch queue");
    }
  }, []);

  // ── Approve Document ────────────────────────────────────

  const approveDocument = useCallback(async (documentId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/vault/approve/${documentId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) throw new Error("Failed to approve document");

      setReviewQueue((prev) => prev.filter((d) => d.id !== documentId));
      setProcessingDocuments((prev) =>
        prev.map((d) =>
          d.id === documentId
            ? { ...d, processing_status: ProcessingStatus.COMPLETE, requires_human_review: false }
            : d
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve");
    }
  }, []);

  // ── Reject / Override Document ──────────────────────────

  const rejectDocument = useCallback(
    async (documentId: string, overrideType: DocumentType) => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/vault/reject/${documentId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ override_type: overrideType }),
        });
        if (!res.ok) throw new Error("Failed to reject document");

        setReviewQueue((prev) => prev.filter((d) => d.id !== documentId));
        setProcessingDocuments((prev) =>
          prev.map((d) =>
            d.id === documentId
              ? {
                  ...d,
                  document_type: overrideType,
                  processing_status: ProcessingStatus.COMPLETE,
                  requires_human_review: false,
                }
              : d
          )
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to reject");
      }
    },
    []
  );

  // ── Fetch Recent Activity ───────────────────────────────

  const fetchActivity = useCallback(async (projectId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/vault/activity/${projectId}`);
      if (!res.ok) throw new Error("Failed to fetch activity");
      const data: VaultActivityItem[] = await res.json();
      setRecentActivity(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch activity");
    }
  }, []);

  // ── Fetch Stats ─────────────────────────────────────────

  const fetchStats = useCallback(async (projectId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/vault/stats/${projectId}`);
      if (!res.ok) throw new Error("Failed to fetch stats");
      const data: VaultStats = await res.json();
      setStats(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch stats");
    }
  }, []);

  // ── Cleanup ─────────────────────────────────────────────

  const cleanup = useCallback(() => {
    pollTimers.current.forEach((timer) => clearInterval(timer));
    pollTimers.current.clear();
  }, []);

  return {
    // State
    uploadProgress,
    processingDocuments,
    reviewQueue,
    recentActivity,
    stats,
    isUploading,
    error,

    // Actions
    uploadDocuments,
    pollStatus,
    getQueue,
    approveDocument,
    rejectDocument,
    fetchActivity,
    fetchStats,
    cleanup,
    setError,
  };
}
