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

  if (requireRole && !hasRole(requireRole) && !user?.is_superuser) {
    return <Navigate to="/" replace />;
  }

  if (requirePermission && !hasPermission(requirePermission)) {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}
