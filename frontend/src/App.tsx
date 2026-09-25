import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Suspense, lazy } from "react";
import { useTranslation } from "react-i18next";
import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import ModuleRoute from "@/components/ModuleRoute";
import EventIndexRedirect from "@/components/EventIndexRedirect";
import ErrorBoundary from "@/components/ErrorBoundary";
import Toaster from "@/components/Toaster";
import ConfirmHost from "@/components/ConfirmHost";
import UpdatePrompt from "@/components/UpdatePrompt";
import { eventRoutes } from "@/core/plugins";
import { useCurrentUser, useRestoreSession } from "@/hooks/useAuth";
import { useAuthStore } from "@/store/authStore";

const LoginPage = lazy(() => import("@/pages/LoginPage"));
const EventSetupPage = lazy(() => import("@/pages/EventSetupPage"));
const PublicEventPage = lazy(() => import("@/pages/PublicEventPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const ForgotPasswordPage = lazy(() => import("@/pages/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("@/pages/ResetPasswordPage"));

function AppRoutes() {
  const { t } = useTranslation();
  const location = useLocation();
  useRestoreSession();
  useCurrentUser();
  const sessionChecked = useAuthStore((state) => state.sessionChecked);
  if (!sessionChecked) return <div className="grid h-screen place-items-center text-gray-500" role="status">{t("restoringSession")}</div>;
  // A failing page (render error, chunk that cannot be loaded) shows an error
  // with a reload button instead of a blank screen; navigating away clears it.
  return <ErrorBoundary resetKey={location.pathname}>
    <Suspense fallback={<div className="grid h-screen place-items-center text-gray-500" role="status">{t("loadingEllipsis")}</div>}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/public/:eventSlug" element={<PublicEventPage />} />
        <Route element={<ProtectedRoute />}>
          <Route index element={<EventIndexRedirect />} />
          <Route path="setup" element={<ProtectedRoute requirePermission="events:write"><EventSetupPage /></ProtectedRoute>} />
          <Route path="settings/*" element={<ProtectedRoute requirePermission="users:read"><SettingsPage /></ProtectedRoute>} />
          <Route path="events/:eventId" element={<Layout />}>
            <Route index element={<Navigate to="dashboard" replace />} />
            {eventRoutes.map(({ path, permission, module, component: Component }) => (
              <Route key={path} path={path} element={<ProtectedRoute requirePermission={permission}><ModuleRoute module={module}><Component /></ModuleRoute></ProtectedRoute>} />
            ))}
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  </ErrorBoundary>;
}

export default function App() {
  return <BrowserRouter>
    <AppRoutes />
    <ConfirmHost />
    <Toaster />
    <UpdatePrompt />
  </BrowserRouter>;
}
