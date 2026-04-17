"use client";

import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import type { VaultProject } from "@/types/vault";
import { ChevronDown } from "lucide-react";

// ── Hardcoded projects matching existing app ────────────────

const PROJECTS: VaultProject[] = [
  {
    id: "proj-tower-a",
    name: "Tower A — Federal Courthouse Annex",
    emoji: "\u{1F3DB}\uFE0F",
    client: "GSA Region 5",
    status: "active",
    phase: "Phase 3 — MEP Rough-In",
    document_count: 247,
  },
  {
    id: "proj-uscis-cooling",
    name: "USCIS & ICE Supplemental Cooling",
    emoji: "\u2744\uFE0F",
    client: "GSA PBS",
    status: "active",
    phase: "Phase 2 — Equipment Install",
    document_count: 183,
  },
  {
    id: "proj-va-elevator",
    name: "VA Hospital — Elevator Modernization",
    emoji: "\u{1F3E5}",
    client: "Dept of Veterans Affairs",
    status: "active",
    phase: "Phase 1 — Demo & Shaft Prep",
    document_count: 126,
  },
  {
    id: "proj-toledo-usps",
    name: "Toledo USPS Station Renovation",
    emoji: "\u{1F4EC}",
    client: "USPS Facilities",
    status: "bidding",
    phase: "Pre-Construction",
    document_count: 54,
  },
  {
    id: "proj-cbp-hvac",
    name: "CBP Port of Entry — HVAC Upgrade",
    emoji: "\u{1F6C2}",
    client: "CBP Facilities",
    status: "active",
    phase: "Phase 2 — Ductwork & Controls",
    document_count: 198,
  },
];

const STATUS_COLORS: Record<string, string> = {
  active: "#34d399",
  bidding: "#fbbf24",
  complete: "#737a90",
};

// ── Component ───────────────────────────────────────────────

interface ProjectSelectorProps {
  selectedProjectId: string | null;
  onSelect: (project: VaultProject) => void;
}

export function ProjectSelector({ selectedProjectId, onSelect }: ProjectSelectorProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selected = PROJECTS.find((p) => p.id === selectedProjectId) ?? null;

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
        Select Project
      </label>

      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "w-full flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all",
          "bg-card/80 backdrop-blur-xl",
          open
            ? "border-[#e8813a] ring-2 ring-[#e8813a]/30"
            : "border-border/50 hover:border-[#e8813a]/40"
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Select a project"
      >
        {selected ? (
          <>
            <span className="text-lg">{selected.emoji}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate" style={{ color: "#e8eaf0" }}>
                {selected.name}
              </p>
              <p className="text-[11px]" style={{ color: "#737a90" }}>
                {selected.client}
              </p>
            </div>
            <span
              className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: `${STATUS_COLORS[selected.status]}20`,
                color: STATUS_COLORS[selected.status],
              }}
            >
              {selected.status}
            </span>
          </>
        ) : (
          <span className="text-sm" style={{ color: "#737a90" }}>
            Choose a project to upload documents...
          </span>
        )}
        <ChevronDown
          className={cn("w-4 h-4 transition-transform shrink-0", open && "rotate-180")}
          style={{ color: "#737a90" }}
        />
      </button>

      {open && (
        <div
          className="absolute z-50 top-full left-0 right-0 mt-1 rounded-xl border border-border/50 bg-[#1c2030] backdrop-blur-xl shadow-xl shadow-black/30 overflow-hidden animate-slide-in"
          role="listbox"
          aria-label="Projects"
        >
          {PROJECTS.map((project) => (
            <button
              key={project.id}
              role="option"
              aria-selected={project.id === selectedProjectId}
              onClick={() => {
                onSelect(project);
                setOpen(false);
              }}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 text-left transition-all",
                "hover:bg-[#e8813a]/10",
                project.id === selectedProjectId && "bg-[#e8813a]/5"
              )}
            >
              <span className="text-lg">{project.emoji}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "#e8eaf0" }}>
                  {project.name}
                </p>
                <p className="text-[11px]" style={{ color: "#737a90" }}>
                  {project.client} · {project.phase}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-[11px] font-medium" style={{ color: "#737a90" }}>
                  {project.document_count} docs
                </span>
                <span
                  className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                  style={{
                    backgroundColor: `${STATUS_COLORS[project.status]}20`,
                    color: STATUS_COLORS[project.status],
                  }}
                >
                  {project.status}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
