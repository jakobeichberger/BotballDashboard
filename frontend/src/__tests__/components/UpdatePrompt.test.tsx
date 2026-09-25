import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import UpdatePrompt from "@/components/UpdatePrompt";

const updateServiceWorker = vi.fn();
const setNeedRefresh = vi.fn();

vi.mock("virtual:pwa-register/react", () => ({
  useRegisterSW: () => ({ needRefresh: [true, setNeedRefresh], offlineReady: [false, vi.fn()], updateServiceWorker }),
}));

describe("UpdatePrompt", () => {
  it("offers the waiting service worker and activates it only on request", () => {
    render(<UpdatePrompt />);
    expect(screen.getByRole("status")).toHaveTextContent("Neue Version verfügbar – neu laden");
    expect(updateServiceWorker).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Neu laden" }));
    // true = send SKIP_WAITING and reload once the new worker controls the page.
    expect(updateServiceWorker).toHaveBeenCalledWith(true);
    fireEvent.click(screen.getByRole("button", { name: "Später" }));
    expect(setNeedRefresh).toHaveBeenCalledWith(false);
  });
});
