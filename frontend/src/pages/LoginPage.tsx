import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff } from "lucide-react";
import { useLogin } from "@/hooks/useAuth";
import { useQueryClient } from "@tanstack/react-query";
import { LogoBadge, Wordmark } from "@/components/BrandMark";

// Two fields validated with react-hook-form's own rules: zod was two thirds
// of the login chunk (the first page every juror loads, often on hall Wi-Fi).
// The server checks the credentials anyway; this only catches typos early.
/** local@domain.tld without spaces (the shape zod's email check accepted). */
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FormData {
  email: string;
  password: string;
}

export default function LoginPage() {
  const { t } = useTranslation("auth");
  const navigate = useNavigate();
  const login = useLogin();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>();

  const onSubmit = async (data: FormData) => {
    try {
      setError(null);
      await login(data.email, data.password);
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      navigate("/");
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 401 || status === 403) {
        setError(t("login.invalidCredentials"));
      } else if (!status) {
        setError(t("login.serverUnreachable"));
      } else {
        setError(t("login.failed", { status }));
      }
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1.1fr)_minmax(26rem,0.9fr)]">
      {/* Brand stage (og image style): tief, grid, red ember glow. */}
      <section className="buehne relative hidden flex-col justify-between overflow-hidden p-12 text-white lg:flex" aria-hidden="true">
        <div className="flex items-center gap-3">
          <LogoBadge />
          <Wordmark onDark className="text-2xl" />
        </div>
        <div className="max-w-xl">
          <p className="eyebrow text-rot-auf-dunkel!">{t("login.heroEyebrow")}</p>
          <p className="mt-4 font-display text-[clamp(2.4rem,4.4vw,3.6rem)] font-extrabold leading-[1.05] tracking-display">
            {t("login.heroTitle")}
          </p>
          <p className="mt-5 text-lg text-sidebar-leise">{t("login.heroText")}</p>
        </div>
        <p className="text-sm text-sidebar-leise">{t("login.subtitle")}</p>
      </section>

      <div className="flex items-center justify-center p-4 sm:p-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 text-center lg:text-left">
            <LogoBadge size="lg" className="mb-4 lg:hidden" />
            <h1 className="text-[2rem] leading-tight">
              <Wordmark />
            </h1>
            <p className="mt-2 text-sm text-leise">{t("login.subtitle")}</p>
          </div>

          <div className="card p-6">
            <h2 className="mb-5 font-ui text-lg font-semibold tracking-ui">{t("login.welcome")}</h2>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div>
                <label className="label" htmlFor="email">{t("login.email")}</label>
                <input
                  id="email"
                  type="email"
                  className="input"
                  placeholder={t("emailPlaceholder")}
                  autoComplete="email"
                  aria-invalid={errors.email ? true : undefined}
                  aria-describedby={errors.email ? "email-error" : undefined}
                  {...register("email", {
                    setValueAs: (value: string) => value.trim(),
                    pattern: { value: EMAIL_PATTERN, message: t("login.invalidEmail") },
                    required: t("login.invalidEmail"),
                  })}
                />
                {errors.email && (
                  <p id="email-error" className="mt-1 text-xs font-medium text-danger">{errors.email.message}</p>
                )}
              </div>
              <div>
                <label className="label" htmlFor="password">{t("login.password")}</label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    className="input pr-11"
                    placeholder="••••••••"
                    autoComplete="current-password"
                    aria-invalid={errors.password ? true : undefined}
                    aria-describedby={errors.password ? "password-error" : undefined}
                    {...register("password", { required: t("login.passwordRequired") })}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-leise hover:text-fg"
                    tabIndex={-1}
                    aria-label={showPassword ? t("login.hidePassword") : t("login.showPassword")}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {errors.password && (
                  <p id="password-error" className="mt-1 text-xs font-medium text-danger">{errors.password.message}</p>
                )}
              </div>

              {error && (
                <div role="alert" className="rounded-eng border border-danger/40 bg-danger/[0.07] px-3 py-2 text-sm font-medium text-danger">
                  {error}
                </div>
              )}

              <button type="submit" className="btn-primary btn-lg w-full" disabled={isSubmitting}>
                {isSubmitting ? t("login.submitting") : t("login.submit")}
              </button>
              <p className="text-center text-sm">
                <Link to="/forgot-password" className="link">
                  {t("login.forgot")}
                </Link>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
