"use client";

import { useState } from "react";
import { Copy, Eye, EyeOff, KeyRound, Plus, Trash2 } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Button, Card, DemoBadge, PageHeader, SectionHeading } from "@/components/ui";

/* DEMO DATA — keys shown are placeholders; no real keys are created here. */

const DEMO_KEYS = [
  { id: "key-1", name: "Production server", prefix: "calle_live_9f2k", created: "12 Sep 2026", lastUsed: "2 hours ago" },
  { id: "key-2", name: "Website widget", prefix: "calle_test_41xq", created: "28 Aug 2026", lastUsed: "3 days ago" },
];

export default function ApiKeysPage() {
  const [revealed, setRevealed] = useState<string[]>([]);

  const toggle = (id: string) =>
    setRevealed((prev) =>
      prev.includes(id) ? prev.filter((key) => key !== id) : [...prev, id],
    );

  return (
    <AppShell>
      <PageHeader
        title="API Keys"
        subtitle="Authenticate your servers and widgets against the Call-E API."
        actions={
          <>
            <DemoBadge />
            <Button>
              <Plus size={16} /> Create key
            </Button>
          </>
        }
      />
      <SectionHeading title="Keys" subtitle="2 active" />
      <Card>
        <ul className="divide-y divide-line-200">
          {DEMO_KEYS.map((key) => {
            const shown = revealed.includes(key.id);
            return (
              <li key={key.id} className="flex flex-wrap items-center gap-3 px-5 py-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-cream-100 text-ink-600">
                  <KeyRound size={17} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-ink-900">{key.name}</span>
                  <span className="mt-0.5 block font-mono text-xs text-ink-500">
                    {shown ? `${key.prefix}_••••••••••••8f3a` : `${key.prefix}_••••••••••••`}
                  </span>
                  <span className="mt-0.5 block text-xs text-ink-500">
                    Created {key.created} · last used {key.lastUsed}
                  </span>
                </span>
                <span className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={shown ? `Hide ${key.name}` : `Reveal ${key.name}`}
                    onClick={() => toggle(key.id)}
                  >
                    {shown ? <EyeOff size={15} /> : <Eye size={15} />}
                  </Button>
                  <Button variant="ghost" size="sm" aria-label={`Copy ${key.name}`}>
                    <Copy size={15} />
                  </Button>
                  <Button variant="ghost" size="sm" aria-label={`Revoke ${key.name}`}>
                    <Trash2 size={15} />
                  </Button>
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
      <p className="mt-3 text-xs text-ink-500">
        Demo shell — creating or revoking here does not touch any real credential store.
      </p>
    </AppShell>
  );
}
