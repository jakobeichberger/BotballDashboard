import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { apiErrorMessage, passwordHint, passwordProblem } from "@/lib/passwordPolicy";

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
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-6 text-center text-2xl font-bold text-gray-900 dark:text-white">
          {t("reset.title")}
        </h1>
        <div className="card p-6 space-y-4">
          {!token ? (
            <p role="alert" className="text-sm text-red-700 dark:text-red-300">
              {t("reset.incompleteLink")}
            </p>
          ) : done ? (
            <p role="status" className="text-sm text-gray-700 dark:text-gray-300">
              {t("reset.done")}
            </p>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <p className="text-xs text-gray-500">{passwordHint()}</p>
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
                <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
                  {error}
                </div>
              )}
              <button type="submit" className="btn-primary w-full justify-center" disabled={busy}>
                {busy ? t("reset.saving") : t("reset.submit")}
              </button>
            </form>
          )}
          <p className="text-center text-sm">
            <Link to={done ? "/login" : "/forgot-password"} className="text-primary-600 hover:underline dark:text-primary-400">
              {done ? t("reset.toLogin") : t("reset.requestNew")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
