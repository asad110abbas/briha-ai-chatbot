import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, KeyRound, LogOut, MoreHorizontal, Pencil, Settings, SquarePen, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { api, del, patch } from "../lib/api";
import type { ConversationSummary } from "../lib/types";
import { Copyright, IconButton, Logo } from "./ui";

function groupLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const days = Math.floor((new Date(today.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 864e5);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "Last 7 days";
  return "Older";
}

const row = "flex min-h-10 w-full items-center gap-2.5 rounded-lg px-3 text-sm transition-colors";

export default function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { conversationId } = useParams();
  const qc = useQueryClient();
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; title: string } | null>(null);
  const { data } = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api<{ items: ConversationSummary[] }>("/conversations?limit=100"),
  });
  const rename = useMutation({
    mutationFn: (v: { id: string; title: string }) => patch(`/conversations/${v.id}`, { title: v.title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => del(`/conversations/${id}`),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (id === conversationId) navigate("/");
    },
  });

  const groups = new Map<string, ConversationSummary[]>();
  for (const c of data?.items ?? []) {
    const g = groupLabel(c.updated_at);
    groups.set(g, [...(groups.get(g) ?? []), c]);
  }
  const name = user?.full_name?.trim() || user?.username || "";

  return (
    <nav className="flex h-full flex-col bg-[#060d18]" aria-label="Conversations">
      <div className="px-3 pb-2 pt-4">
        <div className="px-1"><Logo small /></div>
        <button onClick={() => { navigate("/"); onNavigate?.(); }}
          className={clsx(row, "mt-4 font-medium text-ink hover:bg-white/[0.06]")}>
          <SquarePen size={17} className="text-accent" /> New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-2">
        {[...groups.entries()].map(([label, items]) => (
          <div key={label} className="mb-2">
            <div className="px-3 pb-1 pt-3 text-xs font-medium text-muted">{label}</div>
            {items.map((c) =>
              editing?.id === c.id ? (
                <form key={c.id} className="flex items-center gap-1"
                  onSubmit={(e) => { e.preventDefault(); rename.mutate(editing); setEditing(null); }}>
                  <input autoFocus value={editing.title} aria-label="Conversation title"
                    onChange={(e) => setEditing({ ...editing, title: e.target.value })}
                    className="min-h-9 flex-1 rounded-md border border-line bg-paper px-2 text-sm" />
                  <IconButton label="Save" type="submit" className="h-9 w-9"><Check size={16} /></IconButton>
                  <IconButton label="Cancel" type="button" className="h-9 w-9" onClick={() => setEditing(null)}><X size={16} /></IconButton>
                </form>
              ) : (
                <div key={c.id} className={clsx("group relative flex items-center rounded-lg transition-colors",
                  c.id === conversationId ? "bg-white/[0.07] text-ink" : "text-ink-2 hover:bg-white/[0.04] hover:text-ink")}>
                  <Link to={`/c/${c.id}`} onClick={onNavigate}
                    className="block min-h-9 flex-1 truncate px-3 py-2 text-sm">{c.title}</Link>
                  <IconButton label="Conversation options"
                    className={clsx("h-8 w-8 shrink-0",
                      c.id !== conversationId && menuFor !== c.id && "lg:opacity-0 lg:group-hover:opacity-100 lg:focus:opacity-100")}
                    onClick={() => setMenuFor(menuFor === c.id ? null : c.id)}>
                    <MoreHorizontal size={16} />
                  </IconButton>
                  {menuFor === c.id && (
                    <div className="pop-in absolute right-1 top-9 z-20 w-36 rounded-xl border border-line bg-raised p-1 shadow-[0_12px_32px_rgb(0_0_0/0.6)]">
                      <button className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-white/5"
                        onClick={() => { setEditing({ id: c.id, title: c.title }); setMenuFor(null); }}>
                        <Pencil size={14} /> Rename
                      </button>
                      <button className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-danger hover:bg-white/5"
                        onClick={() => { if (confirm("Delete this chat?")) remove.mutate(c.id); setMenuFor(null); }}>
                        <Trash2 size={14} /> Delete
                      </button>
                    </div>
                  )}
                </div>
              ),
            )}
          </div>
        ))}
        {data && data.items.length === 0 && <p className="px-3 py-3 text-sm text-muted">No chats yet.</p>}
      </div>

      <div className="border-t border-line p-3">
        {user?.role === "admin" && (
          <Link to="/admin" onClick={onNavigate} className={clsx(row, "text-ink-2 hover:bg-white/[0.05] hover:text-ink")}>
            <Settings size={16} /> Settings
          </Link>
        )}
        <Link to="/change-password" onClick={onNavigate} className={clsx(row, "text-ink-2 hover:bg-white/[0.05] hover:text-ink")}>
          <KeyRound size={16} /> Change password
        </Link>
        <div className="mt-2 flex items-center gap-3 rounded-lg px-2 py-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-white">
            {name.charAt(0).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block truncate text-sm text-ink">{name}</span>
            <span className="block truncate text-xs text-muted">@{user?.username}</span>
          </span>
          <IconButton label="Log out" className="h-9 w-9" onClick={() => logout().then(() => navigate("/login"))}>
            <LogOut size={16} />
          </IconButton>
        </div>
        <Copyright className="px-2 pt-2" />
      </div>
    </nav>
  );
}
