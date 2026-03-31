import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

interface Props {
  requireRole?: string;
  children?: React.ReactNode;
}

export default function ProtectedRoute({ requireRole, children }: Props) {
  const { accessToken, hasRole, user } = useAuthStore();

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  if (requireRole && !hasRole(requireRole) && !user?.is_superuser) {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}
