"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  CalendarCheck,
  Check,
  Headset,
  HeartHandshake,
  PartyPopper,
  PhoneCall,
  Sparkles,
  UserRound,
} from "lucide-react";
import { AppShell } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/data-states";
import {
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  StepsIndicator,
  Textarea,
  TextInput,
} from "@/components/ui";
import { agentsApi, knowledgeApi } from "@/lib/api/resources";
import { getTenantId } from "@/lib/tenant";
import { useResource } from "@/lib/use-resource";
import { clsx } from "clsx";

const STEPS = [
  "Identity",
  "Role",
  "Knowledge",
  "Conversation",
  "Voice",
  "Phone",
  "Review",
];

const ROLE_CARDS = [
  { icon: <Briefcase size={20} />, title: "Sales", description: "Qualify leads and pitch products." },
  { icon: <Headset size={20} />, title: "Customer Support", description: "Answer questions, resolve issues." },
  { icon: <UserRound size={20} />, title: "Receptionist", description: "Greet callers and route them." },
  { icon: <HeartHandshake size={20} />, title: "Lead Qualification", description: "Score interest, capture details." },
  { icon: <CalendarCheck size={20} />, title: "Appointment Booking", description: "Offer slots and confirm visits." },
  { icon: <Sparkles size={20} />, title: "Custom", description: "Describe anything else it should do." },
];

const CONVERSATION_STYLES = ["Professional", "Friendly", "Warm", "Direct"] as const;
const RESPONSE_STYLES = ["Natural", "Concise", "Detailed"] as const;

const PERSONALITY_BY_STYLE: Record<string, string> = {
  Professional: "professional",
  Friendly: "friendly and warm",
  Warm: "warm",
  Direct: "direct",
};

function ComingSoon({ children }: { children: React.ReactNode }) {
  return (
    <span className="ml-2 inline-flex items-center rounded-full bg-cream-100 px-2 py-0.5 align-middle text-[11px] font-medium text-ink-500 ring-1 ring-inset ring-line-200">
      {children}
    </span>
  );
}

export default function CreateEmployeePage() {
  const tenantId = getTenantId();
  const [step, setStep] = useState(0);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    description: "",
    role: "Sales",
    roleDescription: "",
    knowledgeSources: [] as string[],
    convStyle: "Friendly",
    responseStyle: "Natural",
    language: "en",
    voiceId: "",
    greeting: "",
  });

  const sources = useResource(() => knowledgeApi.listSources(tenantId));

  const set = (key: keyof typeof form) => (value: string | string[]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  function toggleSource(id: string) {
    setForm((prev) => ({
      ...prev,
      knowledgeSources: prev.knowledgeSources.includes(id)
        ? prev.knowledgeSources.filter((source) => source !== id)
        : [...prev.knowledgeSources, id],
    }));
  }

  const canDeploy =
    form.name.trim().length > 0 && form.role.trim().length > 0;

  async function deploy() {
    if (!canDeploy || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const employee = await agentsApi.create({
        tenant_id: tenantId,
        name: form.name.trim(),
        description: form.description.trim(),
        role: form.role,
        status: "active",
        system_prompt: form.roleDescription.trim(),
        personality:
          PERSONALITY_BY_STYLE[form.convStyle] ?? form.convStyle.toLowerCase(),
        language: form.language,
        voice_id: form.voiceId.trim() || null,
        greeting: form.greeting.trim() || null,
        knowledge_sources: form.knowledgeSources,
      });
      setCreatedId(employee.id);
    } catch (error) {
      setSaveError(
        error instanceof Error ? error.message : "Could not create the employee.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (createdId) {
    return (
      <AppShell>
        <div className="mx-auto max-w-xl py-10 text-center">
          <span className="mx-auto flex size-16 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <PartyPopper size={28} />
          </span>
          <h1 className="mt-6 font-display text-3xl text-ink-900">
            Your AI employee is live.
          </h1>
          <p className="mt-2 text-[15px] text-ink-500">
            {form.name} was created in tenant {tenantId} and is ready to
            configure for calls.
          </p>
          <div className="mt-8 flex justify-center gap-2">
            <Link href="/employees">
              <Button variant="secondary">Back to employees</Button>
            </Link>
            <Link href={`/employees/${encodeURIComponent(createdId)}`}>
              <Button>
                <PhoneCall size={16} /> Open {form.name}
              </Button>
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title="Create AI Employee"
        subtitle={`Creates a real employee in tenant ${tenantId}. Only settings the backend can persist are editable — the rest is marked coming soon.`}
      />
      <div className="mx-auto max-w-3xl">
        <StepsIndicator steps={STEPS} current={step} />

        <Card className="mt-6 p-6 sm:p-8">
          {step === 0 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">Identity</h2>
              <Field label="Employee name">
                <TextInput
                  value={form.name}
                  onChange={(event) => set("name")(event.target.value)}
                  placeholder="e.g. Kaari Sales Assistant"
                />
              </Field>
              <Field label="Description" hint="One line your team will recognise.">
                <Textarea
                  value={form.description}
                  onChange={(event) => set("description")(event.target.value)}
                  placeholder="e.g. Handles inbound product enquiries and lead qualification."
                />
              </Field>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">
                What should {form.name || "your employee"} do?
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {ROLE_CARDS.map((card) => (
                  <button
                    key={card.title}
                    type="button"
                    onClick={() => set("role")(card.title)}
                    aria-pressed={form.role === card.title}
                    className={clsx(
                      "cursor-pointer rounded-xl border p-4 text-left transition-colors",
                      form.role === card.title
                        ? "border-brand-700 bg-brand-50/50"
                        : "border-line-200 hover:border-line-300 hover:bg-cream-50",
                    )}
                  >
                    <span className={form.role === card.title ? "text-brand-700" : "text-ink-500"}>
                      {card.icon}
                    </span>
                    <span className="mt-2 block text-sm font-semibold text-ink-900">
                      {card.title}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-500">
                      {card.description}
                    </span>
                  </button>
                ))}
              </div>
              <Field
                label="Describe what this employee should do"
                hint="Saved as the employee's behavior instructions."
              >
                <Textarea
                  value={form.roleDescription}
                  onChange={(event) => set("roleDescription")(event.target.value)}
                  placeholder="e.g. Answer product questions and collect name + phone for interested buyers. Ask one question at a time."
                />
              </Field>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">
                What should {form.name || "your employee"} know?
              </h2>
              {sources.loading ? (
                <LoadingState label="knowledge sources" />
              ) : sources.error || !sources.data ? (
                <ErrorState
                  message={sources.error ?? "Could not load sources."}
                  onRetry={sources.reload}
                />
              ) : sources.data.length === 0 ? (
                <p className="rounded-xl border border-dashed border-line-300 px-5 py-8 text-center text-sm text-ink-500">
                  No knowledge sources in this tenant yet. Add some on the{" "}
                  <Link href="/knowledge" className="font-medium text-brand-700 hover:text-brand-800">
                    Knowledge page
                  </Link>
                  , then pick them here.
                </p>
              ) : (
                <ul className="divide-y divide-line-200 rounded-xl border border-line-200">
                  {sources.data.map((source) => {
                    const checked = form.knowledgeSources.includes(source.id);
                    return (
                      <li key={source.id}>
                        <label className="flex cursor-pointer items-center gap-3 px-4 py-3">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleSource(source.id)}
                            className="size-4 accent-brand-700"
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block text-sm font-medium text-ink-900">
                              {source.name}
                            </span>
                            <span className="block text-xs text-ink-500">
                              {source.source_type} · {source.status}
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
              <p className="text-xs text-ink-500">
                File uploads and website crawling live on the Knowledge page.
              </p>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              <h2 className="font-display text-xl text-ink-900">
                How should {form.name || "your employee"} talk?
              </h2>
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Conversation style" hint="Saved as personality.">
                  <Select
                    value={form.convStyle}
                    onChange={(event) => set("convStyle")(event.target.value)}
                  >
                    {CONVERSATION_STYLES.map((style) => (
                      <option key={style}>{style}</option>
                    ))}
                  </Select>
                </Field>
                <div className="opacity-60">
                  <Field label="Response style">
                    <Select disabled value={form.responseStyle}>
                      {RESPONSE_STYLES.map((style) => (
                        <option key={style}>{style}</option>
                      ))}
                    </Select>
                  </Field>
                  <ComingSoon>Coming soon</ComingSoon>
                </div>
              </div>
              <div className="rounded-xl border border-line-200 bg-cream-50 p-4 opacity-70">
                <p className="text-sm font-medium text-ink-800">
                  Behavior rules <ComingSoon>Coming soon</ComingSoon>
                </p>
                <p className="mt-1 text-xs text-ink-500">
                  One-question-at-a-time, memory and escalation controls are not
                  separate backend fields yet — describe them in step 2 instead.
                </p>
              </div>
              <div className="rounded-xl bg-cream-100 p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                  Live preview
                </p>
                <p className="mt-2 text-sm text-ink-800">
                  <span className="font-medium text-brand-800">{form.name || "Employee"}:</span>{" "}
                  “Sure. How many planters are you looking for?”
                </p>
                <p className="mt-1 text-xs text-ink-500">
                  {form.convStyle} · one question, then waits.
                </p>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">Voice</h2>
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Language">
                  <Select
                    value={form.language}
                    onChange={(event) => set("language")(event.target.value)}
                  >
                    <option value="en">English</option>
                    <option value="hi">Hindi</option>
                  </Select>
                </Field>
                <Field label="Voice" hint="TTS voice id. Leave empty to use the workspace default voice.">
                  <TextInput
                    value={form.voiceId}
                    onChange={(event) => set("voiceId")(event.target.value)}
                    placeholder="e.g. an ElevenLabs voice id available to your API key"
                  />
                </Field>
              </div>
              <Field
                label="Greeting"
                hint="Spoken first when a call connects. Leave empty for no greeting."
              >
                <Textarea
                  value={form.greeting}
                  onChange={(event) => set("greeting")(event.target.value)}
                  placeholder="e.g. Hello, thank you for calling. How can I help you today?"
                />
              </Field>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">
                Phone <ComingSoon>Coming soon</ComingSoon>
              </h2>
              <p className="rounded-xl border border-dashed border-line-300 px-5 py-8 text-center text-sm text-ink-500">
                Phone numbers, inbound/outbound routing, working hours and
                timezone are not configurable through the API yet. New employees
                use the workspace&apos;s existing dev-phone inbound setup.
              </p>
            </div>
          )}

          {step === 6 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">Review</h2>
              <dl className="divide-y divide-line-200 rounded-xl border border-line-200">
                {(
                  [
                    ["Employee", form.name || "—"],
                    ["Description", form.description || "—"],
                    ["Role", form.role],
                    ["Behavior", form.roleDescription || "—"],
                    ["Knowledge", form.knowledgeSources.length ? form.knowledgeSources.join(", ") : "—"],
                    ["Conversation", form.convStyle],
                    ["Language", form.language],
                    ["Voice", form.voiceId.trim() || "Workspace default"],
                    ["Greeting", form.greeting || "—"],
                    ["Tenant", tenantId],
                  ] as const
                ).map(([term, value]) => (
                  <div key={term} className="flex gap-4 px-4 py-3 text-sm">
                    <dt className="w-28 shrink-0 font-medium text-ink-500">{term}</dt>
                    <dd className="text-ink-800">{value}</dd>
                  </div>
                ))}
              </dl>
              {!canDeploy ? (
                <p className="text-sm text-red-700" role="alert">
                  Give your employee a name and role before deploying.
                </p>
              ) : null}
              {saveError ? (
                <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800" role="alert">
                  Deploy failed: {saveError} — nothing was created.
                </p>
              ) : null}
            </div>
          )}

          <div className="mt-8 flex items-center justify-between border-t border-line-200 pt-5">
            <Button
              variant="ghost"
              disabled={step === 0}
              onClick={() => setStep((value) => Math.max(0, value - 1))}
            >
              <ArrowLeft size={16} /> Back
            </Button>
            {step < STEPS.length - 1 ? (
              <Button onClick={() => setStep((value) => value + 1)}>
                Continue <ArrowRight size={16} />
              </Button>
            ) : (
              <Button onClick={deploy} disabled={!canDeploy || saving}>
                <Check size={16} /> {saving ? "Deploying…" : "Deploy AI Employee"}
              </Button>
            )}
          </div>
        </Card>

        <p className="mt-4 text-center text-xs text-ink-500">
          Step {step + 1} of {STEPS.length} · Deploy creates a real employee via the backend API.
        </p>
      </div>
    </AppShell>
  );
}
