import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Suspense, lazy } from "react";
import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import { useCurrentUser } from "@/hooks/useAuth";

// Lazy-loaded module pages
const ScoreSheetsPage = lazy(
  () => import("@/modules/scoring/score-sheets/pages/ScoreSheetsPage")
);
const ScoreboardPage = lazy(() => import("@/pages/ScoreboardPage"));
const TeamsPage = lazy(() => import("@/pages/TeamsPage"));
const PapersPage = lazy(() => import("@/pages/PapersPage"));
const PrintingPage = lazy(() => import("@/pages/PrintingPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));

function AppRoutes() {
  // Eagerly fetch current user when token is present
  useCurrentUser();

  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-screen text-gray-500">
          Laden...
        </div>
      }
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        {/* Protected routes */}
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="teams" element={<TeamsPage />} />
            <Route path="scoring" element={<ScoreboardPage />} />
            <Route path="scoring/score-sheets" element={<ScoreSheetsPage />} />
            <Route path="papers" element={<PapersPage />} />
            <Route path="printing" element={<PrintingPage />} />
            <Route
              path="settings/*"
              element={
                <ProtectedRoute requireRole="admin">
                  <SettingsPage />
                </ProtectedRoute>
              }
            />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
