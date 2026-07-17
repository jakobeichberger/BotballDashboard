import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Suspense, lazy } from "react";
import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import EventIndexRedirect from "@/components/EventIndexRedirect";
import LoginPage from "@/pages/LoginPage";
import { eventRoutes } from "@/core/plugins";
import { useCurrentUser, useRestoreSession } from "@/hooks/useAuth";
import { useAuthStore } from "@/store/authStore";

const EventSetupPage = lazy(() => import("@/pages/EventSetupPage"));
const PublicEventPage = lazy(() => import("@/pages/PublicEventPage"));

function AppRoutes() {
  useRestoreSession();
  useCurrentUser();
  const sessionChecked = useAuthStore((state) => state.sessionChecked);
  if (!sessionChecked) return <div className="grid h-screen place-items-center text-gray-500">Sitzung wird wiederhergestellt…</div>;
  return <Suspense fallback={<div className="grid h-screen place-items-center text-gray-500">Laden…</div>}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/public/:eventSlug" element={<PublicEventPage />} />
      <Route element={<ProtectedRoute />}>
        <Route index element={<EventIndexRedirect />} />
        <Route path="setup" element={<ProtectedRoute requirePermission="events:write"><EventSetupPage /></ProtectedRoute>} />
        <Route path="events/:eventId" element={<Layout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          {eventRoutes.map(({ path, permission, component: Component }) => (
            <Route key={path} path={path} element={<ProtectedRoute requirePermission={permission}><Component /></ProtectedRoute>} />
          ))}
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </Suspense>;
}

export default function App() { return <BrowserRouter><AppRoutes /></BrowserRouter>; }
