import clsx from "clsx";
import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={clsx(
        "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-brand font-semibold text-white hover:bg-brand-hover",
        variant === "secondary" && "border border-line bg-raised text-ink hover:border-primary/50",
        variant === "ghost" && "text-ink-2 hover:bg-white/5 hover:text-ink",
        variant === "danger" && "border border-danger/40 bg-danger/15 text-danger hover:bg-danger/25",
        className,
      )}
      {...props}
    />
  );
}

export function IconButton({ label, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={clsx(
        "inline-flex h-11 w-11 items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-white/8 hover:text-ink disabled:opacity-40",
        className,
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        "min-h-11 w-full rounded-lg border border-line bg-paper/60 px-3 text-ink transition-shadow placeholder:text-muted focus:border-primary focus:shadow-[0_0_0_4px_rgb(45_212_191/0.12)] focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink-2">{label}</span>
      {children}
    </label>
  );
}

export function ErrorBanner({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="rounded-lg border-l-4 border-danger bg-danger/10 px-3 py-2 text-sm text-danger">
      {children}
    </div>
  );
}

/**
 * The Briha mark: a speech bubble with signal rings around a glowing core (a neutral, original mark).
 * `animated`: the bubble outline draws itself once, then the rings ripple outward and the core glows.
 */
export function BrihaMark({ size = 36, animated = false, className }: {
  size?: number;
  animated?: boolean;
  className?: string;
}) {
  const id = useId();
  const accent = `url(#${id}-accent)`;
  const fine = size >= 44;
  const rings = fine ? [7, 11.5, 16] : [9, 15];
  const stroke = fine ? 2.4 : 3.6;
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className} role="img" aria-label="Briha">
      <defs>
        <linearGradient id={`${id}-accent`} x1="4" y1="4" x2="60" y2="60" gradientUnits="userSpaceOnUse">
          <stop stopColor="#a6ffdc" />
          <stop offset="1" stopColor="#00d68f" />
        </linearGradient>
        <radialGradient id={`${id}-core`}>
          <stop stopColor="#ffffff" />
          <stop offset="0.5" stopColor="#7cc8ff" />
          <stop offset="1" stopColor="#1f8fe0" />
        </radialGradient>
      </defs>
      <path d="M14 6h36a10 10 0 0 1 10 10v26a10 10 0 0 1-10 10H26l-12 9v-9a10 10 0 0 1-10-10V16A10 10 0 0 1 14 6Z"
        fill="none" stroke={accent} strokeWidth={stroke} strokeLinejoin="round" pathLength={1}
        className={animated ? "mark-sheet" : undefined} />
      <g fill="none" stroke={accent} strokeWidth={stroke * 0.6} opacity={0.85}>
        {rings.map((r, i) => (
          <circle key={r} cx="32" cy="29" r={r} className={animated ? "mark-ring" : undefined}
            style={animated ? { animationDelay: `${i * 0.16}s` } : undefined} />
        ))}
      </g>
      <circle cx="32" cy="29" r={fine ? 3.4 : 4.2} fill={`url(#${id}-core)`} className={animated ? "mark-spark" : undefined} />
    </svg>
  );
}

export function Logo({ small = false }: { small?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <BrihaMark size={small ? 34 : 42} />
      <div className="leading-tight">
        <div className={clsx("font-bold tracking-[0.18em] text-ink", small ? "text-base" : "text-lg")}>BRIHA</div>
        <div className="text-xs text-muted">AI Chatbot</div>
      </div>
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("rounded-xl border border-line bg-surface", className)}>{children}</div>;
}

export function Copyright({ className = "" }: { className?: string }) {
  return (
    <div className={`text-center text-xs leading-5 text-muted ${className}`}>
      <p>© {new Date().getFullYear()} Briha AI · MIT License</p>
    </div>
  );
}
