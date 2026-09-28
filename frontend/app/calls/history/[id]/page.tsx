import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Disc3, Timer, Wrench } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Badge, Card, DemoBadge, SectionHeading } from "@/components/ui";
import { demoCallTranscript, getDemoCall } from "@/lib/mock/data";
import { clsx } from "clsx";

/* DEMO DATA — replace with lib/api/resources.ts calls when backend is wired. */

export default async function CallDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const call = getDemoCall(id);
  if (!call) notFound();

  return (
    <AppShell>
      <Link
        href="/calls/history"
        className="inline-flex items-center gap-1 text-sm font-medium text-ink-500 hover:text-ink-900"
      >
        <ArrowLeft size={15} /> Call history
      </Link>

      <div className="mb-8 mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl tracking-tight text-ink-900">
            {call.employee} · {call.customer}
          </h1>
          <p className="mt-2 text-[15px] text-ink-500">
            {call.date} · {call.time} · {call.duration}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DemoBadge />
          <Badge status={call.status} label={call.outcome} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <section>
            <SectionHeading title="Transcript" />
            <Card className="p-6">
              <ol className="space-y-4">
                {demoCallTranscript.map((line, index) => (
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
                        {line.speaker === "ai" ? call.employee : "Customer"} · {line.time}
                      </p>
                      <p className="mt-0.5 text-[15px] leading-relaxed text-ink-900">
                        “{line.text}”
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          </section>

          <section>
            <SectionHeading title="Timeline" />
            <Card className="p-6">
              <ol className="relative space-y-4 border-l border-line-200 pl-5">
                {(
                  [
                    ["00:00", "Call answered"],
                    ["00:12", "Greeting played"],
                    ["00:19", "Customer stated need — 4 planters"],
                    ["00:38", "Size qualifier asked"],
                    ["00:51", "Product recommended — Aqua 20"],
                    [call.duration, `Outcome recorded — ${call.outcome}`],
                  ] as const
                ).map(([time, label]) => (
                  <li key={`${time}-${label}`} className="relative text-sm">
                    <span className="absolute -left-[26px] top-1 size-2 rounded-full bg-brand-600" aria-hidden />
                    <span className="font-medium text-ink-900">{time}</span>
                    <span className="text-ink-500"> · {label}</span>
                  </li>
                ))}
              </ol>
            </Card>
          </section>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <section>
            <SectionHeading title="Outcome" />
            <Card className="p-5">
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-500">Result</dt>
                  <dd className="font-medium text-ink-900">{call.outcome}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-500">Duration</dt>
                  <dd className="font-medium text-ink-900">{call.duration}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-500">Status</dt>
                  <dd><Badge status={call.status} /></dd>
                </div>
              </dl>
            </Card>
          </section>

          <section>
            <SectionHeading title="Tools & actions" />
            <Card className="p-5">
              <ul className="space-y-2.5 text-sm">
                <li className="flex items-center gap-2 text-ink-700">
                  <Wrench size={15} className="text-ink-500" />
                  search_products — “balcony planters”
                </li>
                <li className="flex items-center gap-2 text-ink-700">
                  <Wrench size={15} className="text-ink-500" />
                  calculate_retail_price — Aqua 20 × 4
                </li>
              </ul>
            </Card>
          </section>

          <section>
            <SectionHeading title="Latency" />
            <Card className="p-5">
              <p className="flex items-center gap-2 text-sm text-ink-700">
                <Timer size={15} className="text-ink-500" />
                Avg. speech-end → first audio: <strong>6.4s</strong>
              </p>
              <p className="mt-1 text-xs text-ink-500">
                Streaming TTS · paced RTP · demo figures.
              </p>
            </Card>
          </section>

          <section>
            <SectionHeading title="Recording" />
            <Card className="p-5">
              <p className="flex items-center gap-2 text-sm text-ink-700">
                <Disc3 size={15} className="text-ink-500" />
                Not available
              </p>
              <p className="mt-1 text-xs text-ink-500">
                Call recording storage does not exist in the backend yet — audio
                is intentionally not kept.
              </p>
            </Card>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
