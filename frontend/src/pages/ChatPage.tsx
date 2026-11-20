import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowUp, CalendarDays, Layers, Menu, Package, Scissors, ShieldCheck, Square, SquarePen,
  TrendingUp, Wallet,
} from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router";
import { useAuth } from "../auth/AuthContext";
import AssistantMessage from "../components/AssistantMessage";
import Intro, { shouldShowIntro } from "../components/Intro";
import Sidebar from "../components/Sidebar";
import { BrihaMark, IconButton } from "../components/ui";

// One icon per starter question, in the order of SUGGESTIONS.
const SUGGESTION_ICONS = [Scissors, TrendingUp, Layers, CalendarDays, Package, Wallet];
import { api } from "../lib/api";
import { guessLanguage, SUGGESTIONS, tr } from "../lib/i18n";
import { postSse } from "../lib/sse";
import type { ChatMessage, ConversationSummary, Language } from "../lib/types";

export default function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [intro, setIntro] = useState(() => Boolean(user) && shouldShowIntro(user!.id));
  const [online, setOnline] = useState(navigator.onLine);
  const abortRef = useRef<AbortController | null>(null);
  const skipLoadRef = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const lastLanguage: Language =
    [...messages].reverse().find((m) => m.role === "assistant" && m.language)?.language ?? "english";
  const t = tr(lastLanguage);

  const { data: convs } = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api<{ items: ConversationSummary[] }>("/conversations?limit=100"),
  });
  const title = convs?.items.find((c) => c.id === conversationId)?.title ?? "New chat";

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  useEffect(() => {
    if (skipLoadRef.current && skipLoadRef.current !== conversationId) skipLoadRef.current = null;
    if (!conversationId) {
      if (!busy) setMessages([]);
      return;
    }
    if (skipLoadRef.current === conversationId) return; // just created by this page while streaming
    let cancelled = false;
    api<{ items: ChatMessage[] }>(`/conversations/${conversationId}/messages`)
      .then((r) => !cancelled && setMessages(r.items))
      .catch(() => !cancelled && navigate("/", { replace: true }));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function updatePending(fn: (m: ChatMessage) => ChatMessage) {
    setMessages((ms) => ms.map((m) => (m.pending ? fn(m) : m)));
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    const lang = guessLanguage(message);
    setMessages((ms) => [
      ...ms,
      { id: `u-${Date.now()}`, role: "user", content: message },
      { id: "pending", role: "assistant", content: "", pending: true, language: lang, stage: "understanding" },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;
    let convId = conversationId ?? null;
    try {
      for await (const { event, data } of postSse("/chat", { conversation_id: convId, message }, controller.signal)) {
        if (event === "meta" && !convId) {
          convId = data.conversation_id as string;
          skipLoadRef.current = convId;
          navigate(`/c/${convId}`, { replace: true });
        } else if (event === "status") {
          updatePending((m) => ({ ...m, stage: data.stage }));
        } else if (event === "done") {
          // The finished, checked answer is typed out word by word once all steps are green.
          updatePending(() => ({
            id: data.message_id, role: "assistant", content: data.content, status: data.status,
            language: data.language, animate: true,
            ui_payload: { filters: data.filters, assumptions: data.assumptions, table: data.table,
              clarification_options: data.clarification_options, verified: data.verified },
          }));
        } else if (event === "error") {
          updatePending(() => ({
            id: data.message_id ?? `e-${Date.now()}`, role: "assistant", content: data.message, status: "error",
            language: lang, errorCode: data.code, retryText: message,
          }));
        }
      }
    } catch (err) {
      const stopped = (err as Error).name === "AbortError";
      updatePending(() => ({
        id: `e-${Date.now()}`, role: "assistant", status: "error", language: lang, retryText: message,
        content: stopped ? "Stopped." : "Couldn't reach BRIHA.",
      }));
    } finally {
      setMessages((ms) => ms.map((m) => (m.pending ? { ...m, pending: false } : m)));
      setBusy(false);
      abortRef.current = null;
      qc.invalidateQueries({ queryKey: ["conversations"] });
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    const desktop = window.matchMedia("(min-width: 768px)").matches;
    if (e.key === "Enter" && !e.shiftKey && desktop) {
      e.preventDefault();
      send(input);
    }
  }

  const firstName = user?.full_name?.trim().split(" ")[0] || user?.username || "";
  const empty = messages.length === 0;

  const composer = (
    <form className="composer mx-auto flex w-full max-w-[768px] items-end gap-2 rounded-[28px] border border-line bg-raised/90 p-2 pl-4 shadow-[0_18px_50px_-28px_rgb(0_0_0/0.95)] backdrop-blur-md"
      onSubmit={(e) => { e.preventDefault(); send(input); }}>
      <textarea ref={inputRef} rows={1} value={input} maxLength={1000} onKeyDown={onKeyDown} autoFocus
        onChange={(e) => setInput(e.target.value)} placeholder={t.placeholder} aria-label={t.placeholder}
        className="max-h-40 min-h-10 flex-1 resize-none bg-transparent py-2 text-[15px] placeholder:text-muted focus:outline-none" />
      {busy ? (
        <IconButton type="button" label={t.stop} className="h-10 w-10 rounded-full border border-line bg-surface"
          onClick={() => abortRef.current?.abort()}><Square size={15} className="fill-current" /></IconButton>
      ) : (
        <IconButton type="submit" label={t.send} disabled={!input.trim()}
          className="btn-brand h-10 w-10 rounded-full hover:text-white disabled:opacity-30"><ArrowUp size={18} /></IconButton>
      )}
    </form>
  );
  const footnote = (
    <p className="mx-auto mt-2 flex max-w-[768px] items-center justify-center gap-1.5 text-center text-[11px] text-muted">
      <ShieldCheck size={12} className="text-success" /> BRIHA only reports recorded data. Every number is checked against company data.
    </p>
  );

  return (
    <div className="app-bg flex h-full">
      {intro && user && <Intro userId={user.id} onDone={() => setIntro(false)} />}
      {/* Desktop sidebar */}
      <aside className="hidden w-[280px] shrink-0 border-r border-line lg:block"><Sidebar /></aside>

      {/* Mobile / tablet drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 w-[85%] max-w-[300px] shadow-[0_8px_40px_rgb(0_0_0/0.6)]">
            <Sidebar onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}

      <main className="relative flex min-w-0 flex-1 flex-col">
        <div className="watermark" aria-hidden="true"><span>BRIHA IS A NAME OF IMAM ALI (A.S)</span></div>
        <header className="flex h-12 shrink-0 items-center gap-1 px-2 lg:px-4">
          <IconButton label="Open chats" className="lg:hidden" onClick={() => setDrawer(true)}><Menu size={20} /></IconButton>
          <div className="flex min-w-0 flex-1 items-center justify-center gap-2 font-medium lg:justify-start">
            <BrihaMark size={26} className="shrink-0 lg:hidden" />
            <span className="tracking-[0.16em] lg:hidden">BRIHA</span>
            <span className="hidden truncate text-sm text-ink-2 lg:inline">{empty ? "BRIHA" : title}</span>
          </div>
          <span className="mr-2 hidden items-center gap-1.5 rounded-full border border-line bg-paper/60 px-2.5 py-1 text-xs text-ink-2 lg:inline-flex">
            <span className={clsx("h-1.5 w-1.5 rounded-full", online ? "bg-success" : "bg-warning")} />
            {online ? "Online" : "Offline"}
          </span>
          <IconButton label="New chat" className="lg:hidden" onClick={() => navigate("/")}><SquarePen size={20} /></IconButton>
        </header>

        {busy && <div className="progress-bar top-12" aria-hidden="true" />}
        {!online && <div className="bg-warning px-4 py-1.5 text-center text-sm font-medium text-black">{t.offline}</div>}

        <div className="page-in flex-1 overflow-y-auto" key={conversationId ?? "new"}>
          {empty ? (
            // New chat: greeting and the composer sit together in the middle of the page.
            <div className="flex min-h-full flex-col items-center justify-center px-4 pb-[8vh] pt-6">
              <div className="fade-up halo"><BrihaMark size={72} animated className="relative" /></div>
              <h1 className="fade-up mt-5 text-center text-3xl font-semibold sm:text-4xl" style={{ "--d": "80ms" } as React.CSSProperties}>
                <span className="text-gradient">Welcome{firstName ? `, ${firstName}` : ""}</span>
              </h1>
              <p className="fade-up mt-2 text-center text-ink-2" style={{ "--d": "140ms" } as React.CSSProperties}>
                How can I help with cutting, sales or stock today?
              </p>
              <div className="fade-up mt-8 w-full max-w-[768px]" style={{ "--d": "200ms" } as React.CSSProperties}>{composer}</div>
              <div className="mt-4 grid w-full max-w-[768px] gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s, i) => {
                  const Icon = SUGGESTION_ICONS[i % SUGGESTION_ICONS.length];
                  return (
                    <button key={s} onClick={() => send(s)} style={{ "--d": `${280 + i * 50}ms` } as React.CSSProperties}
                      className="fade-up group flex min-h-12 items-center gap-3 rounded-xl border border-line/70 px-3.5 py-2.5 text-left text-sm text-ink-2 transition-colors hover:border-line hover:bg-white/[0.04] hover:text-ink">
                      <Icon size={16} className="shrink-0 text-accent/80 group-hover:text-accent" />
                      <span className="min-w-0 flex-1">{s}</span>
                    </button>
                  );
                })}
              </div>
              <div className="fade-up" style={{ "--d": "600ms" } as React.CSSProperties}>{footnote}</div>
            </div>
          ) : (
            <div className="mx-auto max-w-[768px] space-y-7 px-4 py-6">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="msg-in flex justify-end">
                    <div className="max-w-[80%] whitespace-pre-wrap break-words rounded-3xl bg-raised px-4 py-2.5 text-[15px] text-ink">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="msg-in flex items-start gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line bg-surface">
                      <BrihaMark size={22} animated={Boolean(m.pending)} />
                    </span>
                    <AssistantMessage message={m} busy={busy} onPick={send} onRetry={send} />
                  </div>
                ),
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {!empty && (
          <div className="shrink-0 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2">
            {composer}
            {footnote}
          </div>
        )}
      </main>
    </div>
  );
}
