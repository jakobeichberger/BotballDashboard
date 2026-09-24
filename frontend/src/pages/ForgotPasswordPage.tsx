import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/passwordPolicy";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/password-reset/request", { email });
      // The server answers the same whether or not the address exists.
      setSent(true);
    } catch (err: any) {
      setError(
        err?.response?.status === 429
          ? "Zu viele Anfragen. Bitte später erneut versuchen."
          : apiErrorMessage(err, "Anfrage fehlgeschlagen."),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-6 text-center text-2xl font-bold text-gray-900 dark:text-white">
          Passwort vergessen
        </h1>
        <div className="card p-6 space-y-4">
          {sent ? (
            <p role="status" className="text-sm text-gray-700 dark:text-gray-300">
              Falls ein Konto mit dieser E-Mail-Adresse existiert, wurde ein Link zum Zurücksetzen
              verschickt. Er ist eine Stunde gültig.
            </p>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Gib die E-Mail-Adresse deines Kontos ein. Du erhältst einen Link, mit dem du ein
                neues Passwort setzen kannst.
              </p>
              <div>
                <label className="label" htmlFor="reset-email">E-Mail</label>
                <input
                  id="reset-email"
                  type="email"
                  required
                  className="input"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              {error && (
                <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
                  {error}
                </div>
              )}
              <button type="submit" className="btn-primary w-full justify-center" disabled={busy || !email}>
                {busy ? "Senden..." : "Link anfordern"}
              </button>
            </form>
          )}
          <p className="text-center text-sm">
            <Link to="/login" className="text-primary-600 hover:underline dark:text-primary-400">
              Zurück zur Anmeldung
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
