import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import NotificationCenter from "@/components/NotificationCenter";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const items = [
  { id: "n1", event_id: "ev", event_type: "print_status_changed", category: "print_status", title: "Print Status Changed", body: "Job a.stl: completed", url: null, created_at: "2026-09-24T10:00:00Z", read: false },
  { id: "n2", event_id: null, event_type: "announcement_published", category: "announcements", title: "Willkommen", body: "Hallo", url: null, created_at: "2026-09-24T09:00:00Z", read: true },
];

function renderCenter() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<NotificationCenter />} />
          <Route path="/events/:eventId/dashboard" element={<h1>Dashboard</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { items, unread: 1 } });
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { marked: 1 } });
  });

  it("shows the unread count and lists the notifications", async () => {
    renderCenter();
    expect(await screen.findByText("1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText("Job a.stl: completed")).toBeInTheDocument();
    expect(screen.getByText("Willkommen")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/dashboard/notifications", { params: { limit: 20 } });
  });

  it("marks a notification read when it is opened and follows it", async () => {
    renderCenter();
    await screen.findByText("1");
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    fireEvent.click(screen.getByText("Job a.stl: completed"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/dashboard/notifications/read", { ids: ["n1"] }));
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("marks everything read", async () => {
    renderCenter();
    await screen.findByText("1");
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    fireEvent.click(screen.getByRole("button", { name: /markAllRead|Alle als gelesen markieren|Mark all as read/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/dashboard/notifications/read-all"));
  });
});
