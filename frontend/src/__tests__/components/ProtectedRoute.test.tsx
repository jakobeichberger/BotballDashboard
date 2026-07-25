import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuthStore } from "@/store/authStore";

function renderRoute() {
  return render(
    <MemoryRouter initialEntries={["/private"]}>
      <Routes>
        <Route path="/" element={<p>Home</p>} />
        <Route path="/login" element={<p>Login</p>} />
        <Route path="/private" element={<ProtectedRoute requirePermission="scoring:write"><p>Scoring form</p></ProtectedRoute>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute permissions", () => {
  beforeEach(() => useAuthStore.setState({ accessToken: null, user: null }));

  it("redirects anonymous users to login", () => {
    renderRoute();
    expect(screen.getByText("Login")).toBeInTheDocument();
  });

  it("blocks an authenticated read-only user", () => {
    useAuthStore.setState({ accessToken: "token", user: { id: "u", is_superuser: false, roles: [], permissions: ["scoring:read"] } as any });
    renderRoute();
    expect(screen.getByText("Home")).toBeInTheDocument();
  });

  it("renders the form for a user with the concrete permission", () => {
    useAuthStore.setState({ accessToken: "token", user: { id: "u", is_superuser: false, roles: [], permissions: ["scoring:write"] } as any });
    renderRoute();
    expect(screen.getByText("Scoring form")).toBeInTheDocument();
  });
});
