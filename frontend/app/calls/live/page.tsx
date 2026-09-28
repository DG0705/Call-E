"use client";

import { useEffect, useState } from "react";
import { Mic, PhoneOff, Signal } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Badge, Button, Card, DemoBadge, PageHeader } from "@/components/ui";
import { demoLiveTranscript } from "@/lib/mock/data";
import { clsx } from "clsx";

/* DEMO DATA — live transcript is a static fixture; no browser audio yet. */

function formatDuration(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function LiveCallsPage() {
  const [elapsed, setElapsed] = useState(47);
  const [speaking, setSpeaking] = useState<"ai" | "customer">("ai");

  useEffect(() => {
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    const voices = setInterval(
      () =>
        setSpeaking((current) => (current === "ai" ? "customer" : "ai")),
      4000,
    );
    return () => {
      clearInterval(timer);
      clearInterval(voices);
    };
  }, []);

  return (
    <AppShell>
      <PageHeader
        title="Live Calls"
        subtitle="One active conversation right now."
        actions={<DemoBadge />}
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="p-6 lg:col-span-2">
          <div className="flex items-center justify-between">
            <Badge status="in-progress" label="LIVE" />
            <span className="flex items-center gap-1.5 text-sm text-ink-500">
              <Signal size={15} className="text-emerald-600" />
              Connected
            </span>
          </div>

          <div className="mt-6 flex items-center gap-4">
            <span className="flex size-14 items-center justify-center rounded-2xl bg-brand-700 font-display text-lg font-semibold text-white">
              KS
            </span>
            <div>
              <p className="font-medium text-ink-900">Kaari Sales Assistant</p>
              <p className="text-sm text-ink-500">talking to +91 98200 12345</p>
            </div>
          </div>

          <p className="mt-6 font-display text-5xl tracking-tight text-ink-900" aria-label="Call duration">
            {formatDuration(elapsed)}
          </p>

          <div className="mt-6 space-y-3">
            <div className="flex items-center gap-3 rounded-xl bg-cream-100 px-4 py-3">
              <span
                className={clsx(
                  "flex size-9 items-center justify-center rounded-full",
                  speaking === "ai"
                    ? "bg-brand-700 text-white"
                    : "bg-white text-ink-500",
                )}
                aria-label={speaking === "ai" ? "AI is speaking" : "AI is listening"}
              >
                <Mic size={16} />
              </span>
              <p className="text-sm text-ink-700">
                {speaking === "ai" ? "AI is speaking…" : "Listening to customer…"}
              </p>
            </div>
            <Button variant="destructive" className="w-full" size="md">
              <PhoneOff size={16} /> End call
            </Button>
            <p className="text-center text-xs text-ink-500">
              Demo controls only — ending here does not affect any real call.
            </p>
          </div>
        </Card>

        <Card className="p-6 lg:col-span-3">
          <h2 className="font-display text-xl text-ink-900">Live transcript</h2>
          <p className="mt-1 text-sm text-ink-500">
            Updates as each side speaks. Transcripts are demo content.
          </p>
          <ol className="mt-5 space-y-4" aria-live="polite">
            {demoLiveTranscript.map((line, index) => (
              <li key={`${line.time}-${index}`} className="flex gap-3">
                <span
                  className={clsx(
                    "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                    line.speaker === "ai"
                      ? "bg-brand-700 text-white"
                      : "bg-cream-200 text-ink-700",
                  )}
                >
                  {line.speaker === "ai" ? "AI" : "CU"}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-ink-500">
                    {line.speaker === "ai" ? "Kaari Sales Assistant" : "Customer"} · {line.time}
                  </p>
                  <p className="mt-0.5 text-[15px] leading-relaxed text-ink-900">
                    “{line.text}”
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </AppShell>
  );
}
