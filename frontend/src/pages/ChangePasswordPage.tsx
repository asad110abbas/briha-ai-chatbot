import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, ErrorBanner, Field, Input, Logo } from "../components/ui";
import { ApiError, post } from "../lib/api";

export default function ChangePasswordPage() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (next !== repeat) return setError("New passwords don't match.");
    setBusy(true);
    setError(null);
    try {
      await post("/auth/change-password", { current_password: current, new_password: next });
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-bg grid min-h-full place-items-center px-4 py-10">
      <Card className="glass w-full max-w-sm rounded-3xl p-7">
        <Logo />
        <h1 className="mt-6 text-xl font-semibold">Change password</h1>
        {user?.must_change_password && (
          <p className="mt-1 text-sm text-ink-2">Please set your own password before continuing.</p>
        )}
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <Field label="Current password">
            <Input type="password" autoComplete="current-password" value={current}
              onChange={(e) => setCurrent(e.target.value)} required />
          </Field>
          <Field label="New password (min 8 characters)">
            <Input type="password" autoComplete="new-password" minLength={8} value={next}
              onChange={(e) => setNext(e.target.value)} required />
          </Field>
          <Field label="Repeat new password">
            <Input type="password" autoComplete="new-password" value={repeat}
              onChange={(e) => setRepeat(e.target.value)} required />
          </Field>
          {error && <ErrorBanner>{error}</ErrorBanner>}
          <div className="flex gap-2">
            {!user?.must_change_password && (
              <Button type="button" variant="secondary" onClick={() => navigate(-1)}>Cancel</Button>
            )}
            <Button type="submit" className="flex-1" disabled={busy}>{busy ? "Saving…" : "Save password"}</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
