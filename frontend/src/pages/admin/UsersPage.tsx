import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, UserCheck, UserX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, Card, ErrorBanner, Field, Input } from "../../components/ui";
import { api, ApiError, patch, post } from "../../lib/api";
import type { Me } from "../../lib/types";
import { PageTitle } from "./AdminLayout";

interface AdminUser extends Me {
  is_active: boolean;
  last_login_at: string | null;
}

function randomPassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
  const arr = crypto.getRandomValues(new Uint32Array(10));
  return Array.from(arr, (n) => chars[n % chars.length]).join("");
}

function CreateUserForm({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ username: "", full_name: "", password: randomPassword(),
    can_view_financials: false, must_change_password: false });
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ username: string; password: string } | null>(null);
  const qc = useQueryClient();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post("/admin/users", f);
      setCreated({ username: f.username, password: f.password });
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create user.");
    }
  }

  if (created)
    return (
      <Card className="mb-5 p-4">
        <p className="font-medium text-success">Account created. Share these credentials directly with the person:</p>
        <p className="mt-2 font-mono text-sm">Username: {created.username}<br />Password: {created.password}</p>
        <Button className="mt-3" variant="secondary" onClick={onDone}>Done</Button>
      </Card>
    );

  return (
    <Card className="mb-5 p-4">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field label="Username"><Input value={f.username} required pattern="[A-Za-z0-9._\-]{3,50}"
          onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
        <Field label="Full name"><Input value={f.full_name} required
          onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
        <Field label="Password">
          <div className="flex gap-2">
            <Input value={f.password} minLength={8} required onChange={(e) => setF({ ...f, password: e.target.value })} />
            <Button type="button" variant="secondary" onClick={() => setF({ ...f, password: randomPassword() })}>Generate</Button>
          </div>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.can_view_financials}
            onChange={(e) => setF({ ...f, can_view_financials: e.target.checked })} /> Can view sales amounts (PKR)
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.must_change_password}
            onChange={(e) => setF({ ...f, must_change_password: e.target.checked })} /> Must change password on first login
        </label>
        {error && <div className="sm:col-span-2"><ErrorBanner>{error}</ErrorBanner></div>}
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit">Create account</Button>
          <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

export default function UsersPage() {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const { data, error } = useQuery({ queryKey: ["admin-users"], queryFn: () => api<{ items: AdminUser[] }>("/admin/users") });
  const update = useMutation({
    mutationFn: (v: { id: string; body: Record<string, unknown> }) => patch(`/admin/users/${v.id}`, v.body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (e) => setNotice(e instanceof ApiError ? e.message : "Update failed"),
  });

  async function resetPassword(u: AdminUser) {
    const pw = randomPassword();
    if (!confirm(`Reset password for ${u.username}? They will be logged out.`)) return;
    try {
      await post(`/admin/users/${u.id}/reset-password`, { new_password: pw, must_change_password: false });
      setNotice(`New password for ${u.username}: ${pw}`);
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Reset failed");
    }
  }

  return (
    <div>
      <PageTitle action={!adding && <Button onClick={() => setAdding(true)}><Plus size={16} /> Add account</Button>}>
        Accounts
      </PageTitle>
      {adding && <CreateUserForm onDone={() => setAdding(false)} />}
      {notice && <div className="mb-4 rounded-lg bg-primary-tint px-3 py-2 font-mono text-sm text-primary">{notice}</div>}
      {error && <ErrorBanner>Could not load users.</ErrorBanner>}
      <div className="grid gap-2">
        {data?.items.map((u) => (
          <Card key={u.id} className="flex flex-wrap items-center gap-3 p-3">
            <div className="min-w-0 flex-1">
              <div className="font-medium">{u.full_name} <span className="text-sm text-muted">@{u.username}</span></div>
              <div className="mt-0.5 flex flex-wrap gap-2 text-xs">
                <span className={u.role === "admin" ? "text-accent" : "text-ink-2"}>{u.role}</span>
                {u.can_view_financials && <span className="text-ink-2">· sees amounts</span>}
                {!u.is_active && <span className="text-danger">· disabled</span>}
                <span className="text-muted">· last login {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "never"}</span>
              </div>
            </div>
            {u.role === "admin" ? (
              <span className="text-sm text-muted">Your administrator account</span>
            ) : (
              <>
                <label className="flex items-center gap-1.5 text-sm text-ink-2">
                  <input type="checkbox" checked={u.can_view_financials}
                    onChange={(e) => update.mutate({ id: u.id, body: { can_view_financials: e.target.checked } })} /> PKR
                </label>
                <Button variant="secondary" onClick={() => resetPassword(u)}><KeyRound size={15} /> Reset</Button>
                <Button variant={u.is_active ? "secondary" : "primary"}
                  onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                  {u.is_active ? <><UserX size={15} /> Disable</> : <><UserCheck size={15} /> Enable</>}
                </Button>
              </>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
