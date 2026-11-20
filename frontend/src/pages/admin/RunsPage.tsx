import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ThumbsDown, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Card, ErrorBanner, IconButton } from "../../components/ui";
import { api, del } from "../../lib/api";
import { PageTitle } from "./AdminLayout";

export const deleteWarning = (username: string) =>
  `Delete this entry from the query log?\n\nIt moves to "Deleted" (with the date and your name) and is erased for good by the normal retention clean-up. @${username}'s chat is not changed.`;

interface Run {
  id: string;
  created_at: string;
  username: string;
  question: string;
  status: string;
  error_code: string | null;
  attempts: number;
  total_latency_ms: number | null;
  cost_usd: number;
  rating: number | null;
  deleted_at: string | null;
  deleted_by: string | null;
}

export const STATUS_COLOR: Record<string, string> = {
  answered: "text-success", clarification: "text-info", no_data: "text-warning", refused: "text-ink-2",
  error: "text-danger",
};

export default function RunsPage() {
  const [status, setStatus] = useState("");
  const [onlyBad, setOnlyBad] = useState(false);
  const [showDeleted, setShowDeleted] = useState(false);
  const qs = new URLSearchParams({ limit: "200", ...(status && { status }), ...(onlyBad && { rating: "-1" }),
    ...(showDeleted && { deleted: "true" }) });
  const { data } = useQuery({ queryKey: ["runs", qs.toString()], queryFn: () => api<{ items: Run[] }>(`/admin/runs?${qs}`) });
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: string) => del(`/admin/runs/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });

  return (
    <div>
      <PageTitle>Query log</PageTitle>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}
          className="min-h-11 rounded-lg border border-line bg-surface px-3">
          <option value="">All statuses</option>
          {Object.keys(STATUS_COLOR).map((s) => <option key={s}>{s}</option>)}
        </select>
        <label className="flex items-center gap-2"><input type="checkbox" checked={onlyBad}
          onChange={(e) => setOnlyBad(e.target.checked)} /> 👎 only</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={showDeleted}
          onChange={(e) => setShowDeleted(e.target.checked)} /> Deleted</label>
        <span className="text-muted">Last 30 days</span>
      </div>
      <div className="grid gap-2">
        {data?.items.map((r) => (
          <div key={r.id} className="flex items-center gap-1">
            <Link to={r.id} className="min-w-0 flex-1">
              <Card className="p-3 hover:border-primary">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                  <span>{new Date(r.created_at).toLocaleString()}</span>
                  <span>@{r.username}</span>
                  <span className={clsx("font-medium", STATUS_COLOR[r.status])}>{r.status}{r.error_code ? ` · ${r.error_code}` : ""}</span>
                  {r.attempts > 1 && <span className="text-warning">retried</span>}
                  <span className="tabular">{r.total_latency_ms ?? "—"} ms</span>
                  <span className="tabular">${r.cost_usd.toFixed(4)}</span>
                  {r.rating === -1 && <ThumbsDown size={13} className="text-danger" />}
                </div>
                <div className="mt-1 truncate">{r.question}</div>
                {r.deleted_at && (
                  <div className="mt-1 text-xs text-danger">
                    Deleted {new Date(r.deleted_at).toLocaleString()}{r.deleted_by ? ` by @${r.deleted_by}` : ""}
                  </div>
                )}
              </Card>
            </Link>
            {!r.deleted_at && (
              <IconButton label="Delete from query log" className="shrink-0 hover:text-danger" disabled={remove.isPending}
                onClick={() => confirm(deleteWarning(r.username)) && remove.mutate(r.id)}>
                <Trash2 size={15} />
              </IconButton>
            )}
          </div>
        ))}
        {remove.isError && <ErrorBanner>Could not delete. Please try again.</ErrorBanner>}
        {data && data.items.length === 0 && (
          <p className="text-sm text-muted">{showDeleted ? "No deleted entries in this period." : "No questions in this period."}</p>
        )}
      </div>
    </div>
  );
}
