import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

interface Props {
  requireRole?: string;
}

export default function ProtectedRoute({ requireRole }: Props) {
  const { accessToken, hasRole, user } = useAuthStore();

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  if (requireRole && !hasRole(requireRole) && !user?.is_superuser) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
