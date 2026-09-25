import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

interface Props {
  requirePermission?: string;
  children?: React.ReactNode;
}

export default function ProtectedRoute({ requirePermission, children }: Props) {
  const { accessToken, hasPermission, user } = useAuthStore();

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  // After a page load the session is back (access token) a moment before the
  // profile with the permissions: wait for it instead of redirecting a deep
  // link or a reload to the start page.
  if (requirePermission && !user) {
    return <div className="p-6 text-gray-500" role="status">Laden…</div>;
  }

  if (requirePermission && !hasPermission(requirePermission)) {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}
