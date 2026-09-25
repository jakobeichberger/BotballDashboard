import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

interface Props {
  requireRole?: string;
  requirePermission?: string;
  children?: React.ReactNode;
}

export default function ProtectedRoute({ requireRole, requirePermission, children }: Props) {
  const { accessToken, hasRole, hasPermission, user } = useAuthStore();

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  // After a page load the session is back (access token) a moment before the
  // profile with the permissions: wait for it instead of redirecting a deep
  // link or a reload to the start page.
  if ((requireRole || requirePermission) && !user) {
    return <div className="p-6 text-gray-500" role="status">Laden…</div>;
  }

  if (requireRole && !hasRole(requireRole) && !user?.is_superuser) {
    return <Navigate to="/" replace />;
  }

  if (requirePermission && !hasPermission(requirePermission)) {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}
