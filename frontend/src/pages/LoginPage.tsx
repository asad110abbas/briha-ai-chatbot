import { ArrowRight, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { BrihaMark, Copyright, ErrorBanner, Field, Input } from "../components/ui";
import { ApiError } from "../lib/api";

// Example questions typed under the sign-in card. Fixed text, not read from any data.
const SAMPLES = [
  "How many sheets were cut today?",
  "How much stock of bleach card do we have?",
  "Show last week's cutting, size wise",
  "What was sold yesterday in 23x36 art paper?",
  "What were the total sales last month?",
];

/** Types each sample question, pauses, erases it, then moves to the next one. */
function useTypewriter(lines: string[]): string {
  const [line, setLine] = useState(0);
  const [count, setCount] = useState(0);
  const [erasing, setErasing] = useState(false);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setCount(lines[line].length);
      return;
    }
    const full = lines[line].length;
    const delay = !erasing && count === full ? 1900 : erasing ? 22 : 48;
    const id = setTimeout(() => {
      if (!erasing && count === full) setErasing(true);
      else if (erasing && count === 0) {
        setErasing(false);
        setLine((line + 1) % lines.length);
      } else setCount(count + (erasing ? -1 : 1));
    }, delay);
    return () => clearTimeout(id);
  }, [count, erasing, line, lines]);
  return lines[line].slice(0, count);
}

function Backdrop() {
  return (
    <div className="login-bg" aria-hidden="true">
      <div className="aurora aurora-1" />
      <div className="aurora aurora-2" />
      <div className="aurora aurora-3" />
      <div className="lattice star-pattern" />
      <div className="motes" />
      <div className="spotlight" />
      <div className="vignette" />
      <div className="watermark"><span>BRIHA IS A NAME OF IMAM ALI (A.S)</span></div>
    </div>
  );
}

const delay = (ms: number) => ({ "--d": `${ms}ms` }) as CSSProperties;

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as { from?: string; expired?: boolean };
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const typed = useTypewriter(SAMPLES);

  if (user) return <Navigate to={state.from ?? "/"} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await login(username, password);
      navigate(me.must_change_password ? "/change-password" : (state.from ?? "/"), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Can't reach BRIHA. Check your connection.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-dvh overflow-hidden"
      onPointerMove={(e) => {
        // A soft light follows the pointer across the backdrop.
        const el = e.currentTarget;
        el.style.setProperty("--mx", `${e.clientX}px`);
        el.style.setProperty("--my", `${e.clientY}px`);
      }}>
      <Backdrop />
      <div className="relative z-10 flex min-h-dvh flex-col items-center px-5 py-8 short:py-4">
        <main className="flex w-full flex-1 flex-col items-center justify-center">
          <div className="fade-up halo short:[&_svg]:h-14 short:[&_svg]:w-auto" style={delay(0)}><BrihaMark size={84} animated className="relative" /></div>
          <h1 className="fade-up mt-5 text-4xl font-bold tracking-[0.24em] sm:text-5xl short:mt-3 short:text-3xl sm:short:text-4xl" style={delay(80)}>
            <span className="text-gradient">BRIHA</span>
          </h1>
          <p className="fade-up mt-3 max-w-sm text-center text-ink-2 short:mt-1" style={delay(160)}>
            Ask your business data <span className="font-medium text-ink">anything</span>
          </p>

          <section className="fade-up glass glow-border mt-8 w-full max-w-[400px] rounded-3xl p-7 short:mt-5 short:p-5" style={delay(240)}>
            <h2 className="text-xl font-semibold">Sign in</h2>
            <p className="mt-1 text-sm text-ink-2">Use the username and password given by your admin.</p>
            {state.expired && state.from && state.from !== "/" && (
              <p className="mt-3 text-sm text-warning">Your session ended. Please sign in again.</p>
            )}
            <form onSubmit={onSubmit} className="mt-6 space-y-4 short:mt-4 short:space-y-3">
              <Field label="Username">
                <Input autoComplete="username" autoCapitalize="none" value={username}
                  onChange={(e) => setUsername(e.target.value)} required />
              </Field>
              <Field label="Password">
                <div className="relative">
                  <Input type={showPassword ? "text" : "password"} autoComplete="current-password" value={password}
                    className="pr-11" onChange={(e) => setPassword(e.target.value)} required />
                  <button type="button" onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-lg text-muted hover:text-ink">
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </Field>
              {error && <ErrorBanner>{error}</ErrorBanner>}
              <button type="submit" disabled={busy}
                className="btn-brand inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-4 text-[15px] font-semibold disabled:cursor-not-allowed disabled:opacity-60">
                {busy ? "Signing in…" : <>Continue <ArrowRight size={17} /></>}
              </button>
            </form>
          </section>

          <div className="fade-up mt-5 flex w-full max-w-[400px] short:hidden items-center gap-3 rounded-2xl border border-line/70 bg-surface/40 px-4 py-3 backdrop-blur"
            style={delay(360)} aria-hidden="true">
            <span className="shrink-0 text-[11px] font-medium uppercase tracking-[0.18em] text-muted">Try</span>
            <span className="caret min-h-6 min-w-0 flex-1 truncate text-sm text-ink-2">{typed}</span>
          </div>
          <p className="fade-up mt-4 inline-flex items-center gap-1.5 text-xs text-muted short:mt-3" style={delay(440)}>
            <ShieldCheck size={14} className="text-success" /> Read-only. Every number is verified against company data.
          </p>
          {/* Right under the card text, so it shows without scrolling on short screens too. */}
          <Copyright className="fade-up mt-5 short:mt-3" />
        </main>
      </div>
    </div>
  );
}
