import clsx from "clsx";
import { ArrowLeft, BarChart3, BookA, ListChecks, Users } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router";
import { Logo } from "../../components/ui";

const NAV = [
  { to: "users", label: "Accounts", icon: Users },
  { to: "glossary", label: "Glossary", icon: BookA },
  { to: "runs", label: "Query log", icon: ListChecks },
  { to: "stats", label: "Usage", icon: BarChart3 },
];

export default function AdminLayout() {
  return (
    <div className="app-bg flex h-full flex-col lg:flex-row">
      <aside className="shrink-0 border-b border-line bg-surface/85 backdrop-blur-md lg:w-[240px] lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between p-4">
          <Logo small />
          <Link to="/" className="flex items-center gap-1 text-sm text-primary hover:underline">
            <ArrowLeft size={14} /> Chat
          </Link>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 lg:flex-col" aria-label="Admin">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => clsx(
              "flex min-h-11 shrink-0 items-center gap-2 rounded-lg px-3 text-sm",
              isActive ? "bg-primary-tint text-primary" : "text-ink-2 hover:bg-white/5 hover:text-ink")}>
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto p-4 lg:p-8">
        <Outlet />
      </main>
    </div>
  );
}

export function PageTitle({ children, action }: { children: string; action?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-xl font-semibold">{children}</h1>
      {action}
    </div>
  );
}
