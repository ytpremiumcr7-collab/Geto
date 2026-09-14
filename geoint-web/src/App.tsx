import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "@/lib/auth";
import { Login } from "@/pages/Login";
import { Dashboard } from "@/pages/Dashboard";
import { Admin } from "@/pages/Admin";
import "./styles/app.css";

function Private({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <Private>
            <Dashboard />
          </Private>
        }
      />
      <Route
        path="/admin"
        element={
          <Private>
            <Admin />
          </Private>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
