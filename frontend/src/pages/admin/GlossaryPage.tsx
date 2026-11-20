import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, Card, ErrorBanner, Input, IconButton } from "../../components/ui";
import { api, ApiError, del, post } from "../../lib/api";
import { PageTitle } from "./AdminLayout";

interface Term {
  id: string;
  kind: string;
  alias: string;
  canonical_value: string;
  notes: string | null;
}

const KINDS = ["paper_type", "size", "customer", "warehouse", "unit", "metric"];

export default function GlossaryPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ kind: "paper_type", alias: "", canonical_value: "" });
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["glossary"], queryFn: () => api<{ items: Term[] }>("/admin/glossary") });
  const remove = useMutation({
    mutationFn: (id: string) => del(`/admin/glossary/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["glossary"] }),
  });

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post("/admin/glossary", form);
      setForm({ ...form, alias: "", canonical_value: "" });
      qc.invalidateQueries({ queryKey: ["glossary"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add.");
    }
  }

  return (
    <div>
      <PageTitle>Glossary</PageTitle>
      <p className="mb-4 max-w-2xl text-sm text-ink-2">
        Teach BRIHA the words your team uses. Example: alias <b>gatta</b> → canonical value <b>DUPLEX</b> means
        "gatta" is understood as Duplex Board. Canonical values must match the codes in the company system.
      </p>
      <Card className="mb-5 p-4">
        <form onSubmit={add} className="flex flex-wrap items-end gap-2">
          <select aria-label="Kind" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}
            className="min-h-11 rounded-lg border border-line bg-surface px-3">
            {KINDS.map((k) => <option key={k}>{k}</option>)}
          </select>
          <Input aria-label="Alias" placeholder="Alias (what people say)" className="w-auto flex-1" required
            value={form.alias} onChange={(e) => setForm({ ...form, alias: e.target.value })} />
          <Input aria-label="Canonical value" placeholder="Canonical code" className="w-auto flex-1" required
            value={form.canonical_value} onChange={(e) => setForm({ ...form, canonical_value: e.target.value })} />
          <Button type="submit">Add</Button>
        </form>
        {error && <div className="mt-3"><ErrorBanner>{error}</ErrorBanner></div>}
      </Card>
      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-paper text-left text-ink-2">
            <tr><th className="px-3 py-2">Kind</th><th className="px-3 py-2">Alias</th><th className="px-3 py-2">Canonical</th><th /></tr>
          </thead>
          <tbody>
            {data?.items.map((t) => (
              <tr key={t.id} className="border-t border-line">
                <td className="px-3 py-1.5 text-muted">{t.kind}</td>
                <td className="px-3 py-1.5">{t.alias}</td>
                <td className="px-3 py-1.5 font-mono text-xs">{t.canonical_value}</td>
                <td className="px-1 text-right">
                  <IconButton label={`Delete ${t.alias}`} onClick={() => confirm(`Delete "${t.alias}"?`) && remove.mutate(t.id)}>
                    <Trash2 size={15} />
                  </IconButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
