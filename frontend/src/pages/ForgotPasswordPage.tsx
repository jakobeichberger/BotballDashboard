import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";

export default function ForgotPasswordPage() {
  const { t } = useTranslation("auth");
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
          ? t("forgot.tooMany")
          : apiErrorMessage(err, t("forgot.failed")),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-papier p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-6 text-center text-2xl font-bold text-fg">
          {t("forgot.title")}
        </h1>
        <div className="card p-6 space-y-4">
          {sent ? (
            <p role="status" className="text-sm text-fg">
              {t("forgot.sent")}
            </p>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <p className="text-sm text-leise">
                {t("forgot.intro")}
              </p>
              <div>
                <label className="label" htmlFor="reset-email">{t("login.email")}</label>
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
                <div role="alert" className="rounded-lg bg-danger/[0.07] px-3 py-2 text-sm text-danger">
                  {error}
                </div>
              )}
              <button type="submit" className="btn-primary w-full justify-center" disabled={busy || !email}>
                {busy ? t("forgot.sending") : t("forgot.submit")}
              </button>
            </form>
          )}
          <p className="text-center text-sm">
            <Link to="/login" className="text-akzent hover:underline">
              {t("forgot.backToLogin")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
