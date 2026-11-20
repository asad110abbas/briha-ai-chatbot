import { useQuery } from "@tanstack/react-query";
import { Card } from "../../components/ui";
import { api } from "../../lib/api";
import { PageTitle } from "./AdminLayout";

interface Stats {
  questions: number;
  active_users: number;
  answered_pct: number;
  clarification_pct: number;
  no_data_pct: number;
  error_pct: number;
  refused_pct: number;
  p50_ms: number | null;
  p95_ms: number | null;
  cost_usd: number;
  thumbs_down: number;
  top_failed: { question: string; count: number }[];
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-2">{hint}</div>}
    </Card>
  );
}

const sec = (ms: number | null) => (ms == null ? "—" : `${(ms / 1000).toFixed(1)} s`);

export default function StatsPage() {
  const { data: s } = useQuery({ queryKey: ["stats"], queryFn: () => api<Stats>("/admin/stats") });
  return (
    <div>
      <PageTitle>Usage · last 30 days</PageTitle>
      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="Questions" value={s.questions.toLocaleString()} hint={`${s.active_users} active users`} />
            <Tile label="Answered" value={`${s.answered_pct}%`}
              hint={`no data ${s.no_data_pct}% · errors ${s.error_pct}%`} />
            <Tile label="Speed" value={sec(s.p50_ms)} hint={`p95 ${sec(s.p95_ms)}`} />
            <Tile label="OpenAI cost" value={`$${s.cost_usd.toFixed(2)}`} hint={`${s.thumbs_down} 👎 ratings`} />
          </div>
          <Card className="mt-5 p-4">
            <h2 className="mb-2 text-sm font-semibold text-ink-2">Questions BRIHA couldn't answer</h2>
            {s.top_failed.length === 0 ? <p className="text-sm text-muted">None 🎉</p> : (
              <ul className="space-y-1 text-sm">
                {s.top_failed.map((f) => (
                  <li key={f.question} className="flex justify-between gap-3">
                    <span className="truncate">{f.question}</span><span className="tabular text-muted">{f.count}×</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
