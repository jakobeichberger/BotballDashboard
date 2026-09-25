import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import Modal from "@/components/Modal";
import ConfirmHost from "@/components/ConfirmHost";
import Toaster from "@/components/Toaster";
import ErrorBoundary, { isChunkLoadError } from "@/components/ErrorBoundary";
import { confirmAction } from "@/lib/confirm";
import { toast, useToastStore } from "@/lib/toast";

function ModalHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open</button>
      <button type="button">Behind</button>
      <Modal open={open} title="Edit team" onClose={() => setOpen(false)}>
        <label htmlFor="name">Name</label>
        <input id="name" />
        <button type="button">Save</button>
      </Modal>
    </>
  );
}

afterEach(() => useToastStore.setState({ toasts: [] }));

describe("Modal", () => {
  it("moves focus in, traps Tab, makes the page inert and restores focus on Escape", async () => {
    const user = userEvent.setup();
    const { container } = render(<ModalHarness />);
    const opener = screen.getByRole("button", { name: "Open" });
    await user.click(opener);

    const dialog = screen.getByRole("dialog", { name: "Edit team" });
    // First form field gets the focus.
    expect(screen.getByLabelText("Name")).toHaveFocus();
    // The page behind the dialog is inert.
    expect(container.closest("[inert]") ?? container.parentElement?.closest("[inert]")).not.toBeNull();

    // Tab cycles within the dialog: input → Save → close (X) → input.
    await user.tab();
    expect(screen.getByRole("button", { name: "Save" })).toHaveFocus();
    await user.tab();
    expect(dialog.querySelector("button[aria-label]")).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText("Name")).toHaveFocus();
    await user.tab({ shift: true });
    expect(dialog.querySelector("button[aria-label]")).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.querySelector("[inert]")).toBeNull();
    expect(opener).toHaveFocus();
  });

  it("is labelled by its title", () => {
    render(<Modal open title="Details" onClose={() => undefined}><p>Body</p></Modal>);
    expect(screen.getByRole("dialog", { name: "Details" })).toHaveAttribute("aria-modal", "true");
  });
});

describe("confirmAction", () => {
  it("resolves true on confirm and false on cancel, focusing Cancel first", async () => {
    render(<ConfirmHost />);
    let result: Promise<boolean> = Promise.resolve(false);
    act(() => { result = confirmAction({ message: "Team „Alpha“ löschen?", tone: "danger" }); });
    const dialog = await screen.findByRole("dialog", { name: "Bitte bestätigen" });
    expect(dialog).toHaveTextContent("Team „Alpha“ löschen?");
    expect(screen.getByRole("button", { name: "Abbrechen" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Löschen" }));
    await expect(result).resolves.toBe(true);

    act(() => { result = confirmAction({ message: "Sicher?" }); });
    fireEvent.click(await screen.findByRole("button", { name: "Abbrechen" }));
    await expect(result).resolves.toBe(false);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("toasts", () => {
  it("shows translated API errors instead of alert() and can be dismissed", async () => {
    render(<Toaster />);
    act(() => { toast.apiError({ response: { status: 409, data: { code: "http_409", message: "Team already registered for this season" } } }); });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Das Team ist für diese Saison bereits angemeldet.");
    fireEvent.click(screen.getByRole("button", { name: "Schließen" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("ErrorBoundary", () => {
  function Broken({ error }: { error: Error }): JSX.Element {
    throw error;
  }

  it("shows a retry instead of a blank page for a render error", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<ErrorBoundary><Broken error={new Error("boom")} /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("Etwas ist schiefgelaufen");
    expect(screen.getByRole("button", { name: "Erneut versuchen" })).toBeInTheDocument();
  });

  it("offers a reload when a lazy chunk cannot be loaded", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const error = new TypeError("Failed to fetch dynamically imported module: https://x/assets/TeamsPage-abc.js");
    expect(isChunkLoadError(error)).toBe(true);
    render(<ErrorBoundary><Broken error={error} /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent(/neue Version/i);
    expect(screen.getByRole("button", { name: /neu laden/i })).toBeInTheDocument();
  });
});
