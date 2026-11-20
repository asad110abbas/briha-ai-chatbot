import { ArrowRight, Clock, Languages, Lock, Package, Scissors, ShieldCheck, TrendingUp } from "lucide-react";
import { useState, type CSSProperties, type ReactNode } from "react";
import { BrihaMark } from "./ui";

function seenKey(userId: string) {
  return `briha-intro-seen:${userId}`;
}

/** True until this user has finished or skipped the introduction in this browser. */
export function shouldShowIntro(userId: string): boolean {
  try {
    return localStorage.getItem(seenKey(userId)) !== "1";
  } catch {
    return false;
  }
}

function markSeen(userId: string) {
  try {
    localStorage.setItem(seenKey(userId), "1");
  } catch {
    // Storage blocked: the introduction simply shows again next time.
  }
}

function Point({ icon, title, text, delay }: { icon: ReactNode; title: string; text: string; delay: number }) {
  return (
    <li className="fade-up glass flex items-start gap-3 rounded-2xl p-4 text-left" style={{ "--d": `${delay}ms` } as CSSProperties}>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-line bg-raised text-accent">{icon}</span>
      <span>
        <span className="block text-sm font-semibold text-ink">{title}</span>
        <span className="mt-0.5 block text-xs leading-5 text-ink-2">{text}</span>
      </span>
    </li>
  );
}

const SLIDES: { eyebrow: string; title: ReactNode; body: ReactNode }[] = [
  {
    eyebrow: "Welcome",
    title: <>Meet <span className="text-gradient">BRIHA</span></>,
    body: (
      <p className="fade-up mx-auto max-w-lg text-lg leading-8 text-ink-2" style={{ "--d": "260ms" } as CSSProperties}>
        Your <span className="font-semibold text-ink">AI data assistant</span>. Ask a question in plain words
        and get the answer from company records in seconds.
      </p>
    ),
  },
  {
    eyebrow: "The name",
    title: <>Why it is called <span className="text-gradient">BRIHA</span></>,
    body: (
      <>
        <p className="fade-up mx-auto max-w-lg text-lg leading-8 text-ink-2" style={{ "--d": "260ms" } as CSSProperties}>
          Briha is a name of <span className="font-semibold text-ink">IMAM ALI (A.S.)</span>, who is remembered for
          knowledge, truth and justice.
        </p>
        <p className="fade-up mx-auto mt-4 max-w-lg text-base leading-7 text-muted" style={{ "--d": "420ms" } as CSSProperties}>
          The assistant carries this name as a promise: to answer truthfully, and to say so plainly when it does not know.
        </p>
      </>
    ),
  },
  {
    eyebrow: "What it does",
    title: <>Ask about your <span className="text-gradient">daily work</span></>,
    body: (
      <ul className="mx-auto grid max-w-2xl gap-3 sm:grid-cols-3">
        <Point delay={240} icon={<Scissors size={17} />} title="Cutting" text="Reels, sheets and weight, by day or by size." />
        <Point delay={340} icon={<TrendingUp size={17} />} title="Sales" text="What was sold, when, and how much." />
        <Point delay={440} icon={<Package size={17} />} title="Stock" text="What is in each godown right now." />
      </ul>
    ),
  },
  {
    eyebrow: "Why it helps",
    title: <>Faster answers, <span className="text-gradient">fewer mistakes</span></>,
    body: (
      <ul className="mx-auto grid max-w-2xl gap-3 sm:grid-cols-2">
        <Point delay={240} icon={<Clock size={17} />} title="Saves time" text="No searching through files or waiting for a report." />
        <Point delay={320} icon={<ShieldCheck size={17} />} title="Checked numbers" text="Every number is verified against company data before you see it." />
        <Point delay={400} icon={<Languages size={17} />} title="Your language" text="Ask in English or Roman Urdu, the way you normally speak." />
        <Point delay={480} icon={<Lock size={17} />} title="Safe and private" text="It only reads data, never changes it. Your chats stay yours." />
      </ul>
    ),
  },
];

/** Full-screen introduction shown once to each new user after their first sign-in. */
export default function Intro({ userId, onDone }: { userId: string; onDone: () => void }) {
  const [step, setStep] = useState(0);
  const last = step === SLIDES.length - 1;
  const slide = SLIDES[step];

  function finish() {
    markSeen(userId);
    onDone();
  }

  return (
    <div className="intro" role="dialog" aria-modal="true" aria-label="Introduction to BRIHA">
      <div className="login-bg" aria-hidden="true">
        <div className="aurora aurora-1" />
        <div className="aurora aurora-2" />
        <div className="lattice star-pattern" />
        <div className="motes" />
        <div className="vignette" />
      </div>
      <button type="button" onClick={finish}
        className="absolute right-4 top-4 z-10 rounded-lg px-3 py-2 text-sm text-ink-2 hover:bg-white/5 hover:text-ink">
        Skip
      </button>

      <div className="relative z-10 flex min-h-full flex-col items-center justify-center px-5 py-16 text-center">
        <div className="halo"><BrihaMark size={96} animated className="relative" /></div>
        <div key={step} className="mt-7 w-full">
          <p className="fade-up text-xs font-semibold uppercase tracking-[0.3em] text-accent">{slide.eyebrow}</p>
          <h2 className="fade-up mt-3 text-3xl font-bold sm:text-5xl" style={{ "--d": "120ms" } as CSSProperties}>{slide.title}</h2>
          <div className="mt-6">{slide.body}</div>
        </div>

        <div className="mt-10 flex items-center gap-2" aria-hidden="true">
          {SLIDES.map((_, i) => (
            <span key={i} className={i === step ? "intro-dot intro-dot-active" : "intro-dot"} />
          ))}
        </div>
        <button type="button" autoFocus onClick={() => (last ? finish() : setStep((s) => Math.min(s + 1, SLIDES.length - 1)))}
          className="btn-brand mt-6 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-7 text-[15px] font-semibold">
          {last ? "Start using BRIHA" : "Next"} <ArrowRight size={17} />
        </button>
      </div>
    </div>
  );
}
