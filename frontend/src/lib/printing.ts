// Shared types and helpers for the 3D printing pages. Local interfaces until
// the generated API client is regenerated with the new printing fields.
import { api } from "@/lib/api";
import i18n from "@/i18n/config";
import { labelMap } from "@/i18n/labels";
import { formatFileSize } from "@/lib/teams";
import { apiErrorMessage } from "@/lib/errors";
import { downloadFile } from "@/lib/download";

export type PrintJobStatus =
  | "pending"
  | "approved"
  | "queued"
  | "printing"
  | "completed"
  | "failed"
  | "cancelled"
  | "rejected";

export interface PrintJob {
  id: string;
  printer_id: string | null;
  team_id: string;
  season_id: string;
  event_id: string | null;
  submitted_by: string | null;
  file_name: string;
  file_url: string | null;
  file_size_bytes: number | null;
  material: string;
  color: string | null;
  /** robot parts count towards the game review's limit of 6; spares and jigs do not. */
  purpose?: "robot" | "spare" | "jig" | string;
  part_count?: number;
  /** Bounding box of the uploaded STL in mm. */
  bbox_x_mm?: number | null;
  bbox_y_mm?: number | null;
  bbox_z_mm?: number | null;
  /** STL handed in with documentation Period 3. */
  stl_submitted?: boolean;
  /** material_not_allowed | color_not_greyscale | exceeds_build_volume */
  rule_warnings?: string[];
  estimated_grams: number | null;
  actual_grams: number | null;
  estimated_minutes: number | null;
  actual_minutes: number | null;
  status: PrintJobStatus;
  priority: number;
  progress: number | null;
  status_message: string | null;
  remaining_seconds: number | null;
  error_message: string | null;
  rejection_reason: string | null;
  quota_override: boolean;
  spool_id: string | null;
  notes: string | null;
  approved_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface PrintJobCreated extends PrintJob {
  quota_warning: string | null;
  /** Set when the team's 3D-print compliance checklist is incomplete. */
  compliance_warning?: string | null;
}

/** PUT /printing/jobs/{id}/cancel: whether a running print was stopped on the printer. */
export interface PrintJobCancelled extends PrintJob {
  printer_cancel?: "sent" | "failed" | "not_applicable" | string;
  printer_message?: string | null;
}

/** Message to show after a cancel, or null when there is nothing to report. */
export function cancelNotice(job: PrintJobCancelled): string | null {
  if (job.printer_cancel === "sent") return `${i18n.t("printing:cancel.sent")} ${job.printer_message ?? ""}`.trim();
  if (job.printer_cancel === "failed") {
    return i18n.t("printing:cancel.failed", { message: job.printer_message ?? i18n.t("printing:cancel.unknownError") });
  }
  return job.printer_message ?? null;
}

export interface PrinterInfo {
  id: string;
  name: string;
  model: string | null;
  printer_type: "bambu" | "octoprint" | "generic" | string;
  is_active: boolean;
  is_online: boolean;
  last_seen: string | null;
  current_state: string | null;
  status_message: string | null;
  // Only returned to printing:admin.
  api_url?: string | null;
  device_id?: string | null;
  notes?: string | null;
}

export interface FilamentSpool {
  id: string;
  printer_id: string | null;
  material: string;
  color: string | null;
  brand: string | null;
  initial_grams: number;
  remaining_grams: number;
  is_active: boolean;
}

export interface PrintQuota {
  id: string;
  team_id: string;
  team_name?: string | null;
  season_id: string;
  event_id: string | null;
  max_parts: number;
  soft_limit_parts: number;
  max_grams: number | null;
  used_parts: number;
  used_grams: number;
  open_parts: number;
  open_grams: number;
  notes: string | null;
}

export const PRINT_FILE_ACCEPT = ".stl,.3mf,.obj,.gcode,.bgcode";

export const STATUS_BADGE: Record<PrintJobStatus, string> = {
  pending: "badge-gray",
  approved: "badge-blue",
  queued: "badge-blue",
  printing: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
  rejected: "badge-red",
};

export const STATUS_LABEL = labelMap<PrintJobStatus>("printing:status", [
  "pending",
  "approved",
  "queued",
  "printing",
  "completed",
  "failed",
  "cancelled",
  "rejected",
]);

export const PRINTER_TYPE_LABEL = labelMap("printing:printerType", ["bambu", "octoprint", "generic"]);

export const PRINTER_STATE_LABEL = labelMap("printing:printerState", ["idle", "printing", "paused", "completed", "failed", "offline"]);

// Mirrors JOB_TRANSITIONS in backend/modules/printing/service.py. Rejecting
// needs a reason and has its own endpoint, so it is not a plain transition.
export const NEXT_STATUSES: Record<PrintJobStatus, PrintJobStatus[]> = {
  pending: ["approved", "cancelled"],
  approved: ["queued", "cancelled"],
  queued: ["printing", "completed", "failed", "cancelled"],
  printing: ["completed", "failed", "cancelled"],
  failed: ["queued", "cancelled"],
  completed: [],
  cancelled: [],
  rejected: [],
};

export const OPEN_STATUSES: PrintJobStatus[] = ["pending", "approved", "queued", "printing"];

/** Refresh interval for job lists and details while prints are running. */
export const PRINT_REFRESH_MS = 10_000;

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

export function formatBytes(bytes: number | null | undefined): string {
  return bytes == null ? "—" : formatFileSize(bytes);
}

/** API error in the UI language (lib/errors). */
export function apiError(error: unknown, fallback = i18n.t("common:actionFailed")): string {
  return apiErrorMessage(error, fallback);
}

export async function uploadPrintFile(jobId: string, file: File): Promise<PrintJob> {
  const body = new FormData();
  body.append("file", file);
  return (await api.post(`/printing/jobs/${jobId}/file`, body)).data;
}

/** The file endpoint needs the bearer token, so fetch it and save the blob. */
export async function downloadPrintFile(job: Pick<PrintJob, "id" | "file_name">): Promise<void> {
  await downloadFile(`/printing/jobs/${job.id}/file`, job.file_name);
}
