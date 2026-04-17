/**
 * Vault Module — TypeScript types for Intelligent Document Vault
 */

// ── Enums ───────────────────────────────────────────────────

export enum DocumentType {
  RFI = "RFI",
  SUBMITTAL = "SUBMITTAL",
  SCHEDULE = "SCHEDULE",
  PLANS_DRAWINGS = "PLANS_DRAWINGS",
  SPECIFICATIONS = "SPECIFICATIONS",
  INVOICE = "INVOICE",
  CHANGE_ORDER = "CHANGE_ORDER",
  PERMIT = "PERMIT",
  COI = "COI",
  DAILY_REPORT = "DAILY_REPORT",
  SAFETY_DOCUMENT = "SAFETY_DOCUMENT",
  PAY_APPLICATION = "PAY_APPLICATION",
  LIEN_WAIVER = "LIEN_WAIVER",
  MEETING_MINUTES = "MEETING_MINUTES",
  BIM_MODEL = "BIM_MODEL",
  PHOTO_PROGRESS = "PHOTO_PROGRESS",
  GEOTECHNICAL = "GEOTECHNICAL",
  SURVEY = "SURVEY",
  CLOSEOUT = "CLOSEOUT",
  TRANSMITTAL = "TRANSMITTAL",
  UNKNOWN = "UNKNOWN",
}

export enum ProcessingStatus {
  PENDING = "PENDING",
  ANALYZING = "ANALYZING",
  CLASSIFIED = "CLASSIFIED",
  ROUTING = "ROUTING",
  COMPLETE = "COMPLETE",
  FAILED = "FAILED",
  NEEDS_REVIEW = "NEEDS_REVIEW",
}

// ── Interfaces ──────────────────────────────────────────────

export interface LibrarianDecision {
  document_type: DocumentType;
  metadata: Record<string, string>;
  confidence_score: number;
  routing_instructions: string;
  workflow_triggers: string[];
  requires_human_review: boolean;
}

export interface VaultDocument {
  id: string;
  filename: string;
  file_size: number;
  mime_type: string;
  document_type: DocumentType;
  confidence_score: number;
  processing_status: ProcessingStatus;
  requires_human_review: boolean;
  created_at: string;
  project_id: string;
  librarian_decision: LibrarianDecision | null;
}

export interface VaultUploadResponse {
  document_ids: string[];
  message: string;
}

export interface WorkflowResult {
  document_id: string;
  actions_taken: string[];
  routing_destination: string;
  success: boolean;
}

// ── Project types used by Vault ─────────────────────────────

export interface VaultProject {
  id: string;
  name: string;
  emoji: string;
  client: string;
  status: "active" | "bidding" | "complete";
  phase: string;
  document_count: number;
}

// ── Activity feed ───────────────────────────────────────────

export interface VaultActivityItem {
  id: string;
  document_id: string;
  filename: string;
  document_type: DocumentType;
  project_name: string;
  processing_status: ProcessingStatus;
  action_summary: string;
  created_at: string;
  librarian_decision: LibrarianDecision | null;
}

// ── Stats ───────────────────────────────────────────────────

export interface VaultStats {
  documents_today: number;
  workflows_triggered: number;
  pending_reviews: number;
  success_rate: number;
}
