// Local API shapes for the team features added with migration 0029 (season
// registration details, season roster, versioned documents, 3D-print
// compliance checklist). Not yet part of the generated client.
import { api } from "@/lib/api";

export type TeamCategory = "botball" | "open" | "aerial" | "jbc";
export type FeeStatus = "pending" | "paid" | "waived";
export type KitStatus = "not_sent" | "sent" | "received";

export interface TeamSeasonRegistration {
  id: string;
  team_id: string;
  season_id: string;
  competition_level_id: string | null;
  registered_at: string;
  confirmed: boolean;
  notes: string | null;
  category: TeamCategory | string;
  fee_status: FeeStatus | string;
  kit_status: KitStatus | string;
  paper_required: boolean;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  address: string | null;
}

export const CATEGORY_LABEL: Record<string, string> = {
  botball: "Botball",
  open: "Open",
  aerial: "Aerial",
  jbc: "JBC",
};
export const FEE_LABEL: Record<string, string> = { pending: "offen", paid: "bezahlt", waived: "erlassen" };
export const FEE_BADGE: Record<string, string> = { pending: "badge-yellow", paid: "badge-green", waived: "badge-gray" };
export const KIT_LABEL: Record<string, string> = { not_sent: "nicht versandt", sent: "versandt", received: "erhalten" };

export type SeasonForm = Pick<
  TeamSeasonRegistration,
  "category" | "fee_status" | "kit_status" | "confirmed" | "notes" | "contact_name" | "contact_email" | "contact_phone" | "address"
>;

/** Body for PUT /teams/{id}/seasons/{season}: mentors send only the contact fields. */
export function seasonPayload(form: SeasonForm, isOrganizer: boolean): Record<string, unknown> {
  const blank = (value: string | null) => (value && value.trim() ? value.trim() : null);
  const contact = {
    contact_name: blank(form.contact_name),
    contact_email: blank(form.contact_email),
    contact_phone: blank(form.contact_phone),
    address: blank(form.address),
  };
  if (!isOrganizer) return contact;
  return {
    ...contact,
    category: form.category,
    fee_status: form.fee_status,
    kit_status: form.kit_status,
    confirmed: form.confirmed,
    notes: blank(form.notes),
  };
}

export interface SeasonRosterEntry {
  id: string;
  member_id: string;
  name: string;
  team_role: string;
  role: string | null;
}

export interface TeamDocumentVersion {
  id: string;
  version_number: number;
  file_name: string;
  media_type: string;
  file_size_bytes: number;
  comment: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
}

export interface TeamDocument {
  id: string;
  team_id: string;
  season_id: string | null;
  title: string;
  category: string;
  description: string | null;
  current_version: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  versions: TeamDocumentVersion[];
}

export const DOCUMENT_CATEGORY_LABEL: Record<string, string> = {
  project_plan: "Projektplan",
  presentation: "Präsentation",
  code_documentation: "Code-Dokumentation",
  other: "Sonstiges",
};

/** PDFs and images; the backend checks the content, not the extension. */
export const DOCUMENT_ACCEPT = "application/pdf,image/png,image/jpeg,image/gif,image/webp,.pdf,.png,.jpg,.jpeg,.gif,.webp";

export interface ComplianceItem {
  id: string;
  season_id: string;
  label: string;
  description: string | null;
  sort_order: number;
  is_active: boolean;
}

export interface ComplianceEntry {
  item: ComplianceItem;
  checked: boolean;
  note: string | null;
  checked_by: string | null;
  checked_at: string | null;
  verified_by: string | null;
  verified_at: string | null;
}

export interface ComplianceStatus {
  team_id: string;
  season_id: string;
  items: ComplianceEntry[];
  total: number;
  checked: number;
  verified: number;
  complete: boolean;
  is_verified: boolean;
}

export function complianceUrl(teamId: string, seasonId: string, suffix = ""): string {
  return `/teams/${teamId}/seasons/${seasonId}/print-compliance${suffix}`;
}

/** Warning text shown before a print job is submitted, or null when nothing is open. */
export function complianceHint(status?: ComplianceStatus | null): string | null {
  if (!status || status.total === 0 || status.complete) return null;
  const open = status.total - status.checked;
  return `Die 3D-Druck-Checkliste des Teams ist unvollständig (${open} von ${status.total} Punkten offen). Der Auftrag wird trotzdem angenommen.`;
}

/** Download a protected file (bearer token) and hand it to the browser. */
export async function downloadBlob(url: string, fileName: string, params?: Record<string, unknown>): Promise<void> {
  const response = await api.get(url, { responseType: "blob", params });
  const href = URL.createObjectURL(new Blob([response.data]));
  try {
    const link = document.createElement("a");
    link.href = href;
    link.download = fileName;
    link.click();
  } finally {
    URL.revokeObjectURL(href);
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// ── Team search ──────────────────────────────────────────────────────────────

export interface TeamFilters {
  q: string;
  country: string;
  status: "" | "active" | "archived";
  season_id: string;
  category: string;
}

export const EMPTY_TEAM_FILTERS: TeamFilters = { q: "", country: "", status: "", season_id: "", category: "" };

/** Query params for GET /teams: empty filters are left out; the team type needs a season. */
export function teamFilterParams(filters: TeamFilters): Record<string, string> {
  const params: Record<string, string> = {};
  if (filters.q.trim()) params.q = filters.q.trim();
  if (filters.country) params.country = filters.country;
  if (filters.status) params.status = filters.status;
  if (filters.season_id) {
    params.season_id = filters.season_id;
    if (filters.category) params.category = filters.category;
  }
  return params;
}
