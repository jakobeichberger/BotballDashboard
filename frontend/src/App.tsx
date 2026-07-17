import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Suspense, lazy } from "react";
import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import EventIndexRedirect from "@/components/EventIndexRedirect";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import { useCurrentUser, useRestoreSession } from "@/hooks/useAuth";
import { useAuthStore } from "@/store/authStore";

const TeamsPage = lazy(() => import("@/pages/TeamsPage"));
const PapersPage = lazy(() => import("@/pages/PapersPage"));
const PrintingPage = lazy(() => import("@/pages/PrintingPage"));
const EventSchedulePage = lazy(() => import("@/pages/EventSchedulePage"));
const EventScoringPage = lazy(() => import("@/pages/EventScoringPage"));
const ScanReviewPage = lazy(() => import("@/pages/ScanReviewPage"));
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
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="teams" element={<ProtectedRoute requirePermission="teams:read"><TeamsPage /></ProtectedRoute>} />
          <Route path="schedule" element={<ProtectedRoute requirePermission="events:read"><EventSchedulePage /></ProtectedRoute>} />
          <Route path="scoring" element={<ProtectedRoute requirePermission="scoring:read"><EventScoringPage /></ProtectedRoute>} />
          <Route path="scans" element={<ProtectedRoute requirePermission="scoring:read"><ScanReviewPage /></ProtectedRoute>} />
          <Route path="papers" element={<ProtectedRoute requirePermission="papers:read"><PapersPage /></ProtectedRoute>} />
          <Route path="printing" element={<ProtectedRoute requirePermission="printing:read"><PrintingPage /></ProtectedRoute>} />
          <Route path="settings" element={<ProtectedRoute requirePermission="events:write"><EventSetupPage /></ProtectedRoute>} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </Suspense>;
}

export default function App() { return <BrowserRouter><AppRoutes /></BrowserRouter>; }
