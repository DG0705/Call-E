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
  UploadCloud,
  UserRound,
  Volume2,
} from "lucide-react";
import { AppShell } from "@/components/shell";
import {
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  StepsIndicator,
  Textarea,
  TextInput,
  Toggle,
} from "@/components/ui";
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

const CONVERSATION_STYLES = ["Professional", "Friendly", "Warm", "Direct"];
const RESPONSE_STYLES = ["Natural", "Concise", "Detailed"];

export default function CreateEmployeePage() {
  const [step, setStep] = useState(0);
  const [deployed, setDeployed] = useState(false);
  const [form, setForm] = useState({
    name: "Sarah",
    description: "Sales assistant for my business",
    role: "Sales",
    roleDescription: "",
    convStyle: "Friendly",
    responseStyle: "Natural",
    oneQuestion: true,
    rememberAnswers: true,
    noOverwhelm: true,
    escalate: true,
    language: "English (India)",
    voice: "Warm female",
    phone: "+91 98200 00000",
    direction: "Inbound",
    hours: "Mon–Sat, 9am–7pm",
    timezone: "Asia/Kolkata",
  });

  const set = (key: keyof typeof form) => (value: string | boolean) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  if (deployed) {
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
            {form.name} is ready to answer calls{form.phone ? ` on ${form.phone}` : ""}.
            This demo stops before real provisioning — connect the backend
            deploy call to go live for customers.
          </p>
          <div className="mt-8 flex justify-center gap-2">
            <Link href="/employees">
              <Button variant="secondary">Back to employees</Button>
            </Link>
            <Link href="/calls/live">
              <Button>
                <PhoneCall size={16} /> Open live calls
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
        subtitle="Seven small steps — no code, no phone-system knowledge needed."
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
                  placeholder="e.g. Sarah"
                />
              </Field>
              <Field
                label="Description"
                hint="One line your team will recognise."
              >
                <Textarea
                  value={form.description}
                  onChange={(event) => set("description")(event.target.value)}
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
              <Field label="Describe what this employee should do">
                <Textarea
                  value={form.roleDescription}
                  onChange={(event) => set("roleDescription")(event.target.value)}
                  placeholder="e.g. Answer product questions for our planter store and collect name + phone for interested buyers."
                />
              </Field>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">
                What should {form.name || "your employee"} know?
              </h2>
              <div className="grid gap-3 sm:grid-cols-3">
                {["Upload documents", "Add website", "Add knowledge source"].map(
                  (action) => (
                    <button
                      key={action}
                      type="button"
                      className="cursor-pointer rounded-xl border border-dashed border-line-300 p-5 text-center transition-colors hover:border-brand-400 hover:bg-brand-50/40"
                    >
                      <UploadCloud size={20} className="mx-auto text-ink-500" />
                      <span className="mt-2 block text-sm font-medium text-ink-800">
                        {action}
                      </span>
                      <span className="mt-0.5 block text-xs text-ink-500">
                        PDF, DOCX, TXT
                      </span>
                    </button>
                  ),
                )}
              </div>
              <div>
                <p className="mb-2 text-sm font-medium text-ink-800">
                  Existing sources
                </p>
                <ul className="divide-y divide-line-200 rounded-xl border border-line-200">
                  {["Product catalog 2026.pdf", "Company website"].map((name) => (
                    <li
                      key={name}
                      className="flex items-center gap-2 px-4 py-2.5 text-sm text-ink-700"
                    >
                      <Check size={15} className="text-emerald-600" />
                      {name}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-ink-500">
                  Document ingestion is not connected yet — uploads are visual only in this demo.
                </p>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              <h2 className="font-display text-xl text-ink-900">
                How should {form.name || "your employee"} talk?
              </h2>
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Conversation style">
                  <Select
                    value={form.convStyle}
                    onChange={(event) => set("convStyle")(event.target.value)}
                  >
                    {CONVERSATION_STYLES.map((style) => (
                      <option key={style}>{style}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Response style">
                  <Select
                    value={form.responseStyle}
                    onChange={(event) => set("responseStyle")(event.target.value)}
                  >
                    {RESPONSE_STYLES.map((style) => (
                      <option key={style}>{style}</option>
                    ))}
                  </Select>
                </Field>
              </div>
              <ul className="divide-y divide-line-200 rounded-xl border border-line-200">
                {(
                  [
                    ["oneQuestion", "Ask one question at a time", "Never rapid-fire a checklist."],
                    ["rememberAnswers", "Remember customer answers", "Never ask for the same detail twice."],
                    ["noOverwhelm", "Don't overwhelm customers", "One or two options, never a catalogue dump."],
                    ["escalate", "Escalate to a human when needed", "Hand off complex or upset callers."],
                  ] as const
                ).map(([key, label, hint]) => (
                  <li key={key} className="flex items-center justify-between gap-4 px-4 py-3">
                    <span>
                      <span className="block text-sm font-medium text-ink-800">{label}</span>
                      <span className="block text-xs text-ink-500">{hint}</span>
                    </span>
                    <Toggle
                      checked={form[key] as boolean}
                      onChange={set(key)}
                      label={label}
                    />
                  </li>
                ))}
              </ul>
              <div className="rounded-xl bg-cream-100 p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                  Live preview
                </p>
                <p className="mt-2 text-sm text-ink-800">
                  <span className="font-medium text-brand-800">{form.name || "Employee"}:</span>{" "}
                  “Sure. How many planters are you looking for?”
                </p>
                <p className="mt-1 text-xs text-ink-500">
                  {form.convStyle} · {form.responseStyle} · one question, then waits.
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
                    <option>English (India)</option>
                    <option>Hindi</option>
                    <option>English (US)</option>
                  </Select>
                </Field>
                <Field label="Voice">
                  <Select
                    value={form.voice}
                    onChange={(event) => set("voice")(event.target.value)}
                  >
                    <option>Warm female</option>
                    <option>Calm male</option>
                    <option>Energetic female</option>
                  </Select>
                </Field>
              </div>
              <Button variant="secondary">
                <Volume2 size={16} /> Preview voice
              </Button>
              <p className="text-xs text-ink-500">
                Voice providers stay abstracted here — no API keys are ever shown.
              </p>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">Phone</h2>
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Phone number">
                  <TextInput
                    value={form.phone}
                    onChange={(event) => set("phone")(event.target.value)}
                  />
                </Field>
                <Field label="Direction">
                  <Select
                    value={form.direction}
                    onChange={(event) => set("direction")(event.target.value)}
                  >
                    <option>Inbound</option>
                    <option>Outbound</option>
                    <option>Both</option>
                  </Select>
                </Field>
                <Field label="Working hours">
                  <TextInput
                    value={form.hours}
                    onChange={(event) => set("hours")(event.target.value)}
                  />
                </Field>
                <Field label="Timezone">
                  <Select
                    value={form.timezone}
                    onChange={(event) => set("timezone")(event.target.value)}
                  >
                    <option>Asia/Kolkata</option>
                    <option>UTC</option>
                    <option>America/New_York</option>
                  </Select>
                </Field>
              </div>
            </div>
          )}

          {step === 6 && (
            <div className="space-y-5">
              <h2 className="font-display text-xl text-ink-900">Review</h2>
              <dl className="divide-y divide-line-200 rounded-xl border border-line-200">
                {(
                  [
                    ["Employee", `${form.name} — ${form.description}`],
                    ["Role", form.roleDescription || form.role],
                    ["Conversation", `${form.convStyle} · ${form.responseStyle}`],
                    ["Voice", `${form.voice} · ${form.language}`],
                    ["Phone", `${form.phone} · ${form.direction} · ${form.hours}`],
                  ] as const
                ).map(([term, value]) => (
                  <div key={term} className="flex gap-4 px-4 py-3 text-sm">
                    <dt className="w-28 shrink-0 font-medium text-ink-500">{term}</dt>
                    <dd className="text-ink-800">{value}</dd>
                  </div>
                ))}
              </dl>
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
              <Button onClick={() => setDeployed(true)}>
                <Check size={16} /> Deploy AI Employee
              </Button>
            )}
          </div>
        </Card>

        <p className="mt-4 text-center text-xs text-ink-500">
          Step {step + 1} of {STEPS.length} · Nothing is provisioned until you deploy.
        </p>
      </div>
    </AppShell>
  );
}
