import { Navigate, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/store/authStore";

interface Props {
  requirePermission?: string;
  children?: React.ReactNode;
}

export default function ProtectedRoute({ requirePermission, children }: Props) {
  const { t } = useTranslation();
  const { accessToken, offlineSession, hasPermission, user } = useAuthStore();

  // An offline cold start signs in read-only from the cached profile.
  if (!accessToken && !offlineSession) {
    return <Navigate to="/login" replace />;
  }

  // After a page load the session is back (access token) a moment before the
  // profile with the permissions: wait for it instead of redirecting a deep
  // link or a reload to the start page.
  if (requirePermission && !user) {
    return <div className="p-6 text-leise" role="status">{t("loadingEllipsis")}</div>;
  }

  if (requirePermission && !hasPermission(requirePermission)) {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}
