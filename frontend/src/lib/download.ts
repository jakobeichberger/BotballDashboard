/**
 * Downloads of protected files. The API authenticates with the bearer token
 * (not a cookie), so a plain <a href="/api/…"> answers 401: fetch the file
 * through the API client and hand the blob to the browser instead.
 */
import { api } from "@/lib/api";

/** "attachment; filename*=UTF-8''sheet%202026.pdf" → "sheet 2026.pdf". */
export function filenameFromDisposition(header: unknown): string | null {
  if (typeof header !== "string") return null;
  const encoded = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim().replace(/^"|"$/g, ""));
    } catch {
      // Malformed encoding: fall back to the plain filename parameter.
    }
  }
  const plain = /filename\s*=\s*("?)([^";]+)\1/i.exec(header);
  return plain ? plain[2].trim() : null;
}

/** Save a blob under `fileName` via a temporary link. */
export function saveBlob(blob: Blob, fileName: string): void {
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = fileName;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoking right away can cancel the download in Firefox and Safari.
  setTimeout(() => URL.revokeObjectURL(href), 60_000);
}

/**
 * Fetch `url` (relative to the API base, "/api" prefix optional) with the
 * session and save it. The file name falls back to the server's
 * Content-Disposition, then to `fallbackName`.
 */
export async function downloadFile(url: string, fileName?: string, params?: Record<string, unknown>, fallbackName = "download"): Promise<void> {
  const response = await api.get<Blob>(url.replace(/^\/api(?=\/)/, ""), { responseType: "blob", params });
  const name = fileName ?? filenameFromDisposition(response.headers?.["content-disposition"]) ?? fallbackName;
  saveBlob(response.data instanceof Blob ? response.data : new Blob([response.data]), name);
}
