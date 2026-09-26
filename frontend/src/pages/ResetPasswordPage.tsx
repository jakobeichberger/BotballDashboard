import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { passwordHint, passwordProblem } from "@/lib/passwordPolicy";
import { apiErrorMessage } from "@/lib/errors";
import { LogoBadge, Wordmark } from "@/components/BrandMark";

export default function ResetPasswordPage() {
  const { t } = useTranslation("auth");
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const problem = passwordProblem(password);
    if (problem) return setError(problem);
    if (password !== confirm) return setError(t("password.mismatch"));
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/password-reset/confirm", { token, new_password: password });
      setDone(true);
    } catch (err: any) {
      setError(apiErrorMessage(err, t("reset.failed")));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-papier p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <LogoBadge size="lg" />
          <Wordmark className="text-xl" />
          <h1 className="page-title mt-2">{t("reset.title")}</h1>
        </div>
        <div className="card p-6 space-y-4">
          {!token ? (
            <p role="alert" className="text-sm text-danger">
              {t("reset.incompleteLink")}
            </p>
          ) : done ? (
            <p role="status" className="text-sm text-fg">
              {t("reset.done")}
            </p>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <p className="text-xs text-leise">{passwordHint()}</p>
              <div>
                <label className="label" htmlFor="new-password">{t("reset.newPassword")}</label>
                <input
                  id="new-password"
                  type="password"
                  className="input"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="confirm-password">{t("reset.confirmPassword")}</label>
                <input
                  id="confirm-password"
                  type="password"
                  className="input"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </div>
              {error && (
                <div role="alert" className="rounded-eng border border-danger/40 bg-danger/[0.07] px-3 py-2 text-sm font-medium text-danger">
                  {error}
                </div>
              )}
              <button type="submit" className="btn-primary btn-lg w-full" disabled={busy}>
                {busy ? t("reset.saving") : t("reset.submit")}
              </button>
            </form>
          )}
          <p className="text-center text-sm">
            <Link to={done ? "/login" : "/forgot-password"} className="link">
              {done ? t("reset.toLogin") : t("reset.requestNew")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
