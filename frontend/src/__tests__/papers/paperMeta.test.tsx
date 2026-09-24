import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DeadlineBanner } from "@/modules/papers/DeadlineBanner";
import { apiErrorMessage, formatCountdown, type PaperDeadline } from "@/modules/papers/paperMeta";

describe("formatCountdown", () => {
  const now = new Date("2026-03-10T12:00:00Z");

  it("shows days and hours when more than a day is left", () => {
    expect(formatCountdown("2026-03-15T23:00:00Z", now)).toBe("5 T 11 Std");
  });

  it("shows hours and minutes on the last day", () => {
    expect(formatCountdown("2026-03-10T15:30:00Z", now)).toBe("3 Std 30 Min");
  });

  it("never shows 0 minutes before the cut-off", () => {
    expect(formatCountdown("2026-03-10T12:00:20Z", now)).toBe("1 Min");
  });

  it("returns null once the deadline has passed", () => {
    expect(formatCountdown("2026-03-10T11:59:00Z", now)).toBeNull();
  });
});

describe("apiErrorMessage", () => {
  it("prefers the API message, then detail, then the fallback", () => {
    expect(apiErrorMessage({ response: { data: { message: "Deadline passed" } } })).toBe("Deadline passed");
    expect(apiErrorMessage({ response: { data: { detail: "Nope" } } })).toBe("Nope");
    expect(apiErrorMessage(new Error("x"), "Fallback")).toBe("Fallback");
  });
});

function deadline(overrides: Partial<PaperDeadline>): PaperDeadline {
  return {
    deadline_date: "2026-03-15",
    timezone: "Europe/Vienna",
    cutoff_at: "2099-03-15T23:00:00Z",
    passed: false,
    locked: false,
    can_override: false,
    ...overrides,
  };
}

describe("DeadlineBanner", () => {
  it("renders nothing without a deadline", () => {
    const { container } = render(<DeadlineBanner deadline={deadline({ cutoff_at: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a countdown before the cut-off", () => {
    render(<DeadlineBanner deadline={deadline({})} />);
    expect(screen.getByText(/einreichungsfrist/i)).toBeInTheDocument();
    expect(screen.getByText(/^noch /)).toBeInTheDocument();
  });

  it("shows the locked state after the cut-off", () => {
    render(<DeadlineBanner deadline={deadline({ cutoff_at: "2020-01-01T00:00:00Z", passed: true, locked: true })} />);
    expect(screen.getByText("Gesperrt")).toBeInTheDocument();
    expect(screen.getByText(/sind gesperrt/i)).toBeInTheDocument();
  });

  it("tells organizers they can override", () => {
    render(
      <DeadlineBanner
        deadline={deadline({ cutoff_at: "2020-01-01T00:00:00Z", passed: true, locked: false, can_override: true })}
      />
    );
    expect(screen.getByText("Admin-Override")).toBeInTheDocument();
  });
});
