import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Button, Card, ErrorBanner } from "../../components/ui";
import { api, del } from "../../lib/api";
import { deleteWarning, STATUS_COLOR } from "./RunsPage";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyJson = any;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="p-4">
      <h2 className="mb-2 text-sm font-semibold text-ink-2">{title}</h2>
      {children}
    </Card>
  );
}

function Json({ value }: { value: AnyJson }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-lg bg-paper p-3 font-mono text-xs leading-relaxed">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export default function RunDetailPage() {
  const { runId } = useParams();
  const { data: run } = useQuery({ queryKey: ["run", runId], queryFn: () => api<AnyJson>(`/admin/runs/${runId}`) });
  const qc = useQueryClient();
  const navigate = useNavigate();
  const remove = useMutation({
    mutationFn: () => del(`/admin/runs/${runId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.removeQueries({ queryKey: ["run", runId] });
      navigate("..", { relative: "path" });
    },
  });
  if (!run) return <p className="text-muted">Loading…</p>;
  const checks: AnyJson[] = run.validation?.final?.checks ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link to=".." relative="path" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
          <ArrowLeft size={14} /> Query log
        </Link>
        {!run.deleted_at && (
          <Button variant="danger" disabled={remove.isPending}
            onClick={() => confirm(deleteWarning(run.username)) && remove.mutate()}>
            <Trash2 size={15} /> Delete
          </Button>
        )}
      </div>
      {remove.isError && <ErrorBanner>Could not delete. Please try again.</ErrorBanner>}
      {run.deleted_at && (
        <ErrorBanner>
          Deleted from the query log on {new Date(run.deleted_at).toLocaleString()}
          {run.deleted_by_username ? ` by @${run.deleted_by_username}` : ""}. It stays here until the retention clean-up erases it.
        </ErrorBanner>
      )}
      <Section title="Question">
        <p className="text-lg">{run.question}</p>
        <p className="mt-1 text-xs text-muted">
          @{run.username} · {new Date(run.created_at).toLocaleString()} ·{" "}
          <span className={clsx("font-medium", STATUS_COLOR[run.final_status])}>{run.final_status}</span>
          {run.error_code && ` · ${run.error_code}`} · attempts {run.attempts} · {run.total_latency_ms} ms ·
          {" "}{run.tokens_input}+{run.tokens_output} tokens · ${run.estimated_cost_usd.toFixed(5)} · {run.datasource_mode}
        </p>
      </Section>
      {run.answer && <Section title="Answer shown to user"><p className="whitespace-pre-wrap">{run.answer}</p></Section>}
      <Section title="Validation (Agent 3)">
        <div className="flex flex-wrap gap-2">
          {checks.map((c) => (
            <span key={c.id} title={c.message ?? ""} className={clsx("rounded-full px-2.5 py-1 text-xs",
              c.pass ? "bg-success/10 text-success" : "bg-danger/10 text-danger")}>
              {c.id} {c.pass ? "✓" : "✗"}{c.valid_zero ? " (valid zero)" : ""}
            </span>
          ))}
          {run.validation?.final?.llm_verdict && (
            <span className="rounded-full bg-paper px-2.5 py-1 text-xs">LLM judge: {run.validation.final.llm_verdict}</span>
          )}
        </div>
        {run.validation?.final?.fix_hint && <p className="mt-2 text-sm text-warning">{run.validation.final.fix_hint}</p>}
      </Section>
      <Section title="Plan (Agent 1)"><Json value={run.plan} /></Section>
      <Section title="Resolved filters"><Json value={run.resolved_filters} /></Section>
      <Section title="Tool calls (Agent 2)"><Json value={run.tool_calls} /></Section>
      <Section title="Result preview"><Json value={run.result_preview} /></Section>
      <Section title="Stage latency (ms)"><Json value={run.stage_latency_ms} /></Section>
      {run.validation?.attempts?.length > 1 && <Section title="All attempts"><Json value={run.validation.attempts} /></Section>}
    </div>
  );
}
