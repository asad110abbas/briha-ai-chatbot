import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Copy, Info, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { post } from "../lib/api";
import { STAGES, tr } from "../lib/i18n";
import type { ChatMessage, Language, Table } from "../lib/types";
import { Button, IconButton } from "./ui";

export function StatusSteps({ stage, language }: { stage?: ChatMessage["stage"]; language: Language }) {
  const t = tr(language);
  const active = stage ? STAGES.indexOf(stage) : 0;
  return (
    <ol className="space-y-1.5 py-1 text-sm" aria-live="polite">
      {STAGES.map((s, i) => (
        <li key={s} className={clsx("flex items-center gap-2", i > active ? "text-muted" : "text-ink-2")}>
          <span className={clsx("h-2 w-2 rounded-full", i < active && "bg-success",
            i === active && "pulse-dot bg-primary", i > active && "bg-line")} />
          {t.stages[s]}
        </li>
      ))}
    </ol>
  );
}

const TICK_MS = 30;
const MAX_TICKS = 80; // long answers type faster so none takes more than ~2.5 s

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Reveals `text` word by word when `on`; returns the visible part and whether typing has finished. */
function useTypewriter(text: string, on: boolean): [string, boolean] {
  const tokens = useRef(text.split(/(\s+)/));
  const animate = on && !prefersReducedMotion() && tokens.current.length > 1;
  const [shown, setShown] = useState(animate ? 0 : tokens.current.length);

  useEffect(() => {
    if (!animate) return;
    const total = tokens.current.length;
    const step = Math.max(2, Math.ceil(total / MAX_TICKS));
    const id = setInterval(() => {
      setShown((n) => {
        const next = Math.min(total, n + step);
        if (next >= total) clearInterval(id);
        return next;
      });
    }, TICK_MS);
    return () => clearInterval(id);
  }, [animate]);

  const done = shown >= tokens.current.length;
  return [done ? text : tokens.current.slice(0, shown).join(""), done];
}

function fmt(v: string | number | null): string {
  if (v === null || v === undefined) return "—";
  return typeof v === "number" ? v.toLocaleString("en-US") : v;
}

function DataTable({ table }: { table: Table }) {
  const [all, setAll] = useState(false);
  const rows = all ? table.rows : table.rows.slice(0, 20);
  return (
    <div className="mt-3">
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm tabular">
          <thead className="bg-paper text-left text-ink-2">
            <tr>{table.columns.map((c, i) => (
              <th key={c} className={clsx("whitespace-nowrap px-3 py-2 font-medium",
                i === 0 && "sticky left-0 bg-paper", i > 0 && "text-right")}>{c}</th>))}</tr>
          </thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri} className="border-t border-line">
                {r.map((v, i) => (
                  <td key={i} className={clsx("whitespace-nowrap px-3 py-1.5",
                    i === 0 && "sticky left-0 bg-surface", i > 0 && "text-right")}>{fmt(v)}</td>))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.rows.length > 20 && !all && (
        <button className="mt-1 text-sm text-primary hover:underline" onClick={() => setAll(true)}>
          Show all {table.rows.length} rows
        </button>
      )}
    </div>
  );
}

function Feedback({ message }: { message: ChatMessage }) {
  const t = tr(message.language);
  const [rating, setRating] = useState<number | null>(message.rating ?? null);
  const [asking, setAsking] = useState(false);
  const [comment, setComment] = useState("");
  const [copied, setCopied] = useState(false);
  const send = (r: number, c?: string) => post(`/messages/${message.id}/feedback`, { rating: r, comment: c });

  return (
    <>
      <div className="-ml-2 mt-1 flex items-center gap-0.5 [&>button]:h-8 [&>button]:w-8 [&>button]:text-muted">
        <IconButton label="Copy answer" onClick={() => {
          navigator.clipboard?.writeText(message.content);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}><Copy size={16} /></IconButton>
        {copied && <span className="text-xs text-success">Copied</span>}
        <IconButton label="Good answer" className={clsx(rating === 1 && "text-success")}
          onClick={() => { setRating(1); setAsking(false); send(1); }}><ThumbsUp size={16} /></IconButton>
        <IconButton label="Bad answer" className={clsx(rating === -1 && "text-danger")}
          onClick={() => { setRating(-1); setAsking(true); send(-1); }}><ThumbsDown size={16} /></IconButton>
      </div>
      {asking && (
        <form className="mt-1 flex gap-2" onSubmit={(e) => { e.preventDefault(); send(-1, comment); setAsking(false); }}>
          <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t.whatWrong}
            aria-label={t.whatWrong} className="min-h-10 flex-1 rounded-lg border border-line bg-paper px-3 text-sm" />
          <Button type="submit" variant="secondary">OK</Button>
        </form>
      )}
    </>
  );
}

export default function AssistantMessage({ message, onPick, onRetry, busy }: {
  message: ChatMessage;
  onPick: (option: string) => void;
  onRetry: (text: string) => void;
  busy: boolean;
}) {
  const language: Language = message.language ?? "english";
  const t = tr(language);
  const ui = message.ui_payload ?? {};
  const [visible, typed] = useTypewriter(message.content, Boolean(message.animate));
  const boxRef = useRef<HTMLDivElement>(null);

  // Keep the newest words in view while the answer is being typed.
  useEffect(() => {
    if (message.animate && !typed) boxRef.current?.scrollIntoView({ block: "end" });
  }, [visible, typed, message.animate]);

  if (message.pending && !message.content) {
    return (
      <div className="min-w-0 flex-1 pt-0.5">
        <StatusSteps stage={message.stage} language={language} />
      </div>
    );
  }

  const isError = message.status === "error";
  const isNoData = message.status === "no_data";
  return (
    <div ref={boxRef} className={clsx("min-w-0 flex-1 text-[15px] leading-7",
      isError ? "rounded-xl border border-danger/40 bg-danger/10 px-4 py-3" : "pt-0.5")}>
      <div className="flex gap-2">
        {isError && <AlertTriangle size={18} className="mt-0.5 shrink-0 text-danger" />}
        {isNoData && <Info size={18} className="mt-0.5 shrink-0 text-muted" />}
        <div className="answer min-w-0 flex-1 break-words">
          <ReactMarkdown>{visible}</ReactMarkdown>
        </div>
      </div>

      {/* Table, filters and buttons appear once the text has finished typing. */}
      {typed && <>
      {ui.table && <DataTable table={ui.table} />}

      {ui.filters && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {Object.entries(ui.filters).map(([k, v]) => (
            <span key={k} className="rounded-full border border-primary/20 bg-primary-tint px-2.5 py-1 text-xs text-primary">{k}: {v}</span>
          ))}
        </div>
      )}

      {ui.assumptions && ui.assumptions.length > 0 && (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-accent"><Info size={15} className="mt-0.5 shrink-0" />
          {ui.assumptions.join(" ")}</p>
      )}

      {message.status === "clarification" && ui.clarification_options && ui.clarification_options.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {ui.clarification_options.map((o) => (
            <button key={o} disabled={busy} onClick={() => onPick(o)}
              className="min-h-10 rounded-full border border-primary px-4 text-sm text-primary hover:bg-primary-tint disabled:opacity-50">
              {o}
            </button>
          ))}
        </div>
      )}

      {isError && message.retryText && (
        <Button variant="secondary" className="mt-3" disabled={busy} onClick={() => onRetry(message.retryText!)}>
          <RotateCcw size={16} /> {t.retry}
        </Button>
      )}

      {message.status === "answered" && !message.pending && (
        <>
          {ui.verified && (
            <div className="mt-2 flex items-center gap-1 text-xs text-success">
              <CheckCircle2 size={14} /> {t.verified}
            </div>
          )}
          <Feedback message={message} />
        </>
      )}
      </>}
    </div>
  );
}
