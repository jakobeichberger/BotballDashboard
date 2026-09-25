import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ScoreSheetsPage from "@/modules/scoring/score-sheets/pages/ScoreSheetsPage";
import ConfirmHost from "@/components/ConfirmHost";
import { api } from "@/lib/api";
import { filenameFromDisposition } from "@/lib/download";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

const SHEET = { id: "sh1", label: "Botball 2026", year: 2026, game_theme: null, is_active: false, file_name: "sheet.pdf", ocr_status: "done", confirmed_fields_count: null, uploaded_at: "" };

function renderPage() {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string, config?: { responseType?: string }) => {
    if (url === "/seasons/active") return Promise.resolve({ data: { id: "s1" } });
    if (url === "/scoring/seasons/s1/score-sheets") return Promise.resolve({ data: [SHEET] });
    if (config?.responseType === "blob") return Promise.resolve({ data: new Blob(["%PDF"]), headers: { "content-disposition": 'attachment; filename="sheet.pdf"' } });
    return Promise.resolve({ data: [] });
  });
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ScoreSheetsPage />
        <ConfirmHost />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ScoreSheetsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("downloads the PDF with the session instead of a plain (401) link", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { container } = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "PDF von Botball 2026 herunterladen" }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/scoring/score-sheets/sh1/file", expect.objectContaining({ responseType: "blob" })));
    expect(container.querySelector("a[href*='/file']")).toBeNull();
    await waitFor(() => expect(click).toHaveBeenCalled());
    click.mockRestore();
  });

  it("has no interactive elements nested in the select button and confirms deleting", async () => {
    const { container } = renderPage();
    const select = await screen.findByRole("button", { name: /Botball 2026/, pressed: false });
    expect(select.querySelector("button, a")).toBeNull();
    expect(container.querySelectorAll("button button, button a")).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Botball 2026 löschen" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Abbrechen" }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("reads the file name from Content-Disposition", () => {
    expect(filenameFromDisposition('attachment; filename="a b.pdf"')).toBe("a b.pdf");
    expect(filenameFromDisposition("attachment; filename*=UTF-8''W%C3%BCrfel.pdf")).toBe("Würfel.pdf");
    expect(filenameFromDisposition(undefined)).toBeNull();
  });
});
