import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { EventLink } from "@/components/EventLink";
import { scopeToEvent } from "@/hooks/useEventPath";
import { eventRoutes } from "@/core/plugins";

describe("scopeToEvent", () => {
  it("puts app paths under the current event", () => {
    expect(scopeToEvent("/teams/42", "e1")).toBe("/events/e1/teams/42");
    expect(scopeToEvent("/papers", "e1")).toBe("/events/e1/papers");
  });

  it("leaves global paths alone", () => {
    for (const path of ["/events/e2/teams", "/login", "/public/ecer", "/setup", "/settings/users"]) {
      expect(scopeToEvent(path, "e1")).toBe(path);
    }
  });

  it("leaves relative paths and event-less contexts alone", () => {
    expect(scopeToEvent("details", "e1")).toBe("details");
    expect(scopeToEvent("/teams/42", undefined)).toBe("/teams/42");
  });
});

describe("EventLink", () => {
  it("renders an href scoped to the event in the URL", () => {
    render(
      <MemoryRouter initialEntries={["/events/e7/teams"]}>
        <Routes>
          <Route path="/events/:eventId/teams" element={<EventLink to="/teams/42">Team</EventLink>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Team" })).toHaveAttribute("href", "/events/e7/teams/42");
  });
});

describe("event route registry", () => {
  // Every path a page links to must actually be registered, or the link 404s
  // into the catch-all redirect.
  const linkedPaths = [
    "teams",
    "teams/matrix",
    "teams/:id",
    "bots",
    "bots/:id",
    "papers/:id",
    "printing/jobs/:id",
    "scoreboard",
    "scoring/entry",
    "scoring/de",
    "scoring/aerial",
    "scoring/doc",
    "scoring/score-sheets",
    "profile",
  ];

  it.each(linkedPaths)("registers %s", (path) => {
    expect(eventRoutes.map((route) => route.path)).toContain(path);
  });

  it("has no duplicate paths", () => {
    const paths = eventRoutes.map((route) => route.path);
    expect(new Set(paths).size).toBe(paths.length);
  });
});
