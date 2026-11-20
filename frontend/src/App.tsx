import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import { useAuth } from "./auth/AuthContext";
import AdminLayout from "./pages/admin/AdminLayout";
import GlossaryPage from "./pages/admin/GlossaryPage";
import RunDetailPage from "./pages/admin/RunDetailPage";
import RunsPage from "./pages/admin/RunsPage";
import StatsPage from "./pages/admin/StatsPage";
import UsersPage from "./pages/admin/UsersPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";

function RequireAuth({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { user, loading, signedOut } = useAuth();
  const location = useLocation();
  if (loading) return <div className="grid h-full place-items-center text-muted">Loading…</div>;
  // Pressing "Log out" goes to a clean sign-in page; only a session that ended on its own shows the notice.
  if (!user) return signedOut ? <Navigate to="/login" replace />
    : <Navigate to="/login" replace state={{ from: location.pathname, expired: true }} />;
  if (user.must_change_password && location.pathname !== "/change-password")
    return <Navigate to="/change-password" replace />;
  if (admin && user.role !== "admin") return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/change-password" element={<RequireAuth><ChangePasswordPage /></RequireAuth>} />
      <Route path="/" element={<RequireAuth><ChatPage /></RequireAuth>} />
      <Route path="/c/:conversationId" element={<RequireAuth><ChatPage /></RequireAuth>} />
      <Route path="/admin" element={<RequireAuth admin><AdminLayout /></RequireAuth>}>
        <Route index element={<Navigate to="users" replace />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="glossary" element={<GlossaryPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="stats" element={<StatsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
