import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/auth/AuthContext";
import { AppShell } from "@/layout/AppShell";
import { Login } from "@/pages/Login";
import { Dashboard } from "@/pages/Dashboard";
import { Admin } from "@/pages/Admin";
import { OnboardingPage } from "@/pages/OnboardingPage";
import { PermissionsPage } from "@/pages/PermissionsPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { AlertsPage } from "@/pages/AlertsPage";
import "./styles/app.css";

function Private({ children }: { children: React.ReactNode }) {
  const { authenticated, loading } = useAuth();
  if (loading) return <p className="page-pad muted">…</p>;
  if (!authenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <Private>
            <AppShell />
          </Private>
        }
      >
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/map" element={<Dashboard />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/permissions" element={<PermissionsPage />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/" element={<Navigate to="/map" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/map" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
