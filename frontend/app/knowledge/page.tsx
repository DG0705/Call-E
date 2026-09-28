import { FileText, Globe, Type, UploadCloud } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Button, Card, DemoBadge, PageHeader, SectionHeading } from "@/components/ui";
import { demoKnowledgeSources } from "@/lib/mock/data";

/* DEMO DATA — uploads are visual only; ingestion is not connected yet. */

const KIND_ICON = {
  document: <FileText size={17} />,
  website: <Globe size={17} />,
  text: <Type size={17} />,
} as const;

export default function KnowledgePage() {
  return (
    <AppShell>
      <PageHeader
        title="Knowledge"
        subtitle="Give your AI employees the documents, websites and notes they should answer from."
        actions={<DemoBadge />}
      />

      <SectionHeading title="Add a source" />
      <div className="grid gap-3 sm:grid-cols-3">
        {(
          [
            ["Upload documents", "PDF, DOCX, TXT up to 50MB"],
            ["Add website", "Crawl public pages and help centres"],
            ["Add a note", "Paste policies, prices, FAQs"],
          ] as const
        ).map(([title, hint]) => (
          <button
            key={title}
            type="button"
            className="cursor-pointer rounded-xl border border-dashed border-line-300 bg-white p-6 text-center transition-colors hover:border-brand-400 hover:bg-brand-50/40"
          >
            <UploadCloud size={22} className="mx-auto text-ink-500" />
            <span className="mt-2 block text-sm font-medium text-ink-900">{title}</span>
            <span className="mt-0.5 block text-xs text-ink-500">{hint}</span>
          </button>
        ))}
      </div>

      <div className="mt-10">
        <SectionHeading
          title="Sources"
          subtitle="3 sources · 186 chunks indexed"
          action={<Button variant="secondary" size="sm">Re-index all</Button>}
        />
        <Card>
          <ul className="divide-y divide-line-200">
            {demoKnowledgeSources.map((source) => (
              <li key={source.id} className="flex items-center gap-4 px-5 py-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-cream-100 text-ink-600">
                  {KIND_ICON[source.kind as keyof typeof KIND_ICON]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink-900">
                    {source.name}
                  </span>
                  <span className="block text-xs text-ink-500">
                    {source.items} chunks · updated {source.updated}
                  </span>
                </span>
                <Button variant="ghost" size="sm">Edit</Button>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}
