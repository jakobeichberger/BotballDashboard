import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Layout from "@/components/Layout";
import ModuleRoute from "@/components/ModuleRoute";
import { isModuleEnabled, type EventModules } from "@/hooks/useEventModules";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const modules: EventModules = {
  event_id: "ev",
  available_modules: ["seeding", "double_elimination", "paper", "documentation", "aerial", "printing", "bots"],
  active_modules: ["seeding", "printing", "aerial"],
  effective_modules: ["seeding", "printing"],
  season_flags: { use_aerial: false, use_paper_scoring: true },
};

function mockApi() {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url === "/v1/events/ev/modules") return Promise.resolve({ data: modules });
    if (url === "/dashboard/notifications") return Promise.resolve({ data: { items: [], unread: 0 } });
    if (url === "/v1/events") return Promise.resolve({ data: [] });
    return Promise.resolve({ data: null });
  });
}

function renderAt(path: string, element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/events/:eventId" element={<Layout />}>
            <Route path="*" element={element} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("isModuleEnabled", () => {
  it("uses the effective modules, any-of for lists", () => {
    expect(isModuleEnabled(modules, "printing")).toBe(true);
    expect(isModuleEnabled(modules, "aerial")).toBe(false);
    expect(isModuleEnabled(modules, "paper")).toBe(false);
    expect(isModuleEnabled(modules, ["documentation", "paper_scoring"])).toBe(true);
    expect(isModuleEnabled({ ...modules, season_flags: {} }, ["documentation", "paper_scoring"])).toBe(false);
  });

  it("fails open while the module state is unknown", () => {
    expect(isModuleEnabled(undefined, "paper")).toBe(true);
    expect(isModuleEnabled(modules, undefined)).toBe(true);
  });
});

describe("module-aware navigation and routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
    useAuthStore.setState({
      accessToken: "tok",
      user: { id: "u1", display_name: "Admin", is_superuser: true, roles: [] } as never,
    });
  });

  it("hides navigation entries of disabled modules", async () => {
    renderAt("/events/ev/dashboard", <p>Inhalt</p>);
    expect(await screen.findByRole("link", { name: /3D-Druck|3D printing/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("link", { name: /Paper-Review|Paper review/ })).not.toBeInTheDocument());
    expect(screen.queryByRole("link", { name: /Roboter|Robots/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Teams/ })).toBeInTheDocument();
  });

  it("guards routes of disabled modules", async () => {
    renderAt("/events/ev/papers", <ModuleRoute module="paper"><h1>Papers</h1></ModuleRoute>);
    expect(await screen.findByText(/nicht aktiv|not active/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Papers" })).not.toBeInTheDocument();
  });

  it("renders routes of enabled modules", async () => {
    renderAt("/events/ev/printing", <ModuleRoute module="printing"><h1>Druck</h1></ModuleRoute>);
    expect(await screen.findByRole("heading", { name: "Druck" })).toBeInTheDocument();
  });
});
