"use client";

import { useState, useEffect } from "react";
import { useVault } from "@/hooks/useVault";
import type { VaultProject } from "@/types/vault";
import { VaultStats } from "./VaultStats";
import { ProjectSelector } from "./ProjectSelector";
import { UploadZone } from "./UploadZone";
import { LibrarianStatus } from "./LibrarianStatus";
import { VaultActivity } from "./VaultActivity";
import { ReviewQueue } from "./ReviewQueue";

// ── VaultPage ───────────────────────────────────────────────

export function VaultPage() {
  const [selectedProject, setSelectedProject] = useState<VaultProject | null>(null);

  const {
    uploadProgress,
    processingDocuments,
    reviewQueue,
    recentActivity,
    stats,
    isUploading,
    error,
    uploadDocuments,
    approveDocument,
    rejectDocument,
    fetchActivity,
    fetchStats,
    cleanup,
    setError,
  } = useVault();

  // Fetch data when project changes
  useEffect(() => {
    if (selectedProject) {
      fetchStats(selectedProject.id);
      fetchActivity(selectedProject.id);
    }
  }, [selectedProject, fetchStats, fetchActivity]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  const handleUpload = (files: File[]) => {
    if (!selectedProject) return;
    uploadDocuments(files, selectedProject.id);
  };

  const handleProjectSelect = (project: VaultProject) => {
    setSelectedProject(project);
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h2 className="text-xl font-bold" style={{ color: "#e8eaf0" }}>
            {"\u{1F5C4}\uFE0F"} Document Vault
          </h2>
          <p className="text-sm mt-1" style={{ color: "#737a90" }}>
            Drop anything. AI handles the rest.
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div
            className="mb-4 px-4 py-3 rounded-xl border flex items-center justify-between animate-slide-in"
            style={{
              backgroundColor: "rgba(248, 113, 113, 0.08)",
              borderColor: "rgba(248, 113, 113, 0.2)",
            }}
          >
            <p className="text-sm" style={{ color: "#f87171" }}>
              {error}
            </p>
            <button
              onClick={() => setError(null)}
              className="text-xs font-medium px-2 py-1 rounded-md transition-all hover:bg-[#2a2f42]"
              style={{ color: "#f87171" }}
              aria-label="Dismiss error"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Review Queue banner — shown when items exist */}
        <div className="mb-4">
          <ReviewQueue
            items={reviewQueue}
            onApprove={approveDocument}
            onReject={rejectDocument}
          />
        </div>

        {/* Stats bar */}
        <div className="mb-6">
          <VaultStats stats={stats} />
        </div>

        {/* Two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left column — Project + Upload */}
          <div className="space-y-5">
            <ProjectSelector
              selectedProjectId={selectedProject?.id ?? null}
              onSelect={handleProjectSelect}
            />
            <UploadZone
              projectSelected={selectedProject !== null}
              isUploading={isUploading}
              uploadProgress={uploadProgress}
              onUpload={handleUpload}
            />
          </div>

          {/* Right column — Librarian + Activity */}
          <div className="space-y-5">
            <LibrarianStatus documents={processingDocuments} />
            <VaultActivity activities={recentActivity} />
          </div>
        </div>
      </div>
    </div>
  );
}
