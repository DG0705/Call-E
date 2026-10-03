import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { clsx } from "clsx";

/* ---------- Buttons ---------- */

type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const buttonStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-700 text-white shadow-sm hover:bg-brand-800 active:bg-brand-900",
  secondary:
    "bg-white text-ink-800 border border-line-300 shadow-sm hover:border-line-300 hover:bg-cream-100",
  ghost: "text-ink-700 hover:bg-cream-100",
  destructive:
    "bg-white text-red-700 border border-red-200 shadow-sm hover:bg-red-50",
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        "inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2 text-sm",
        buttonStyles[variant],
        className,
      )}
      {...props}
    />
  );
}

/* ---------- Cards & sections ---------- */

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "rounded-xl border border-line-200 bg-white shadow-[0_1px_2px_rgba(32,29,27,0.05)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SectionHeading({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="font-display text-xl text-ink-900">{title}</h2>
        {subtitle ? (
          <p className="mt-1 text-sm text-ink-500">{subtitle}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-3xl tracking-tight text-ink-900">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-2 max-w-2xl text-[15px] text-ink-500">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/* ---------- Status badge ---------- */

const statusStyles: Record<string, string> = {
  live: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  active: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  paused: "bg-amber-50 text-amber-700 ring-amber-600/25",
  draft: "bg-stone-100 text-ink-600 ring-ink-500/20",
  "in-progress": "bg-brand-50 text-brand-700 ring-brand-600/20",
  error: "bg-red-50 text-red-700 ring-red-600/20",
  failed: "bg-red-50 text-red-700 ring-red-600/20",
  missed: "bg-stone-100 text-ink-600 ring-ink-500/20",
};

export function Badge({ status, label }: { status: string; label?: string }) {
  const key = status.toLowerCase();
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        statusStyles[key] ?? "bg-stone-100 text-ink-600 ring-ink-500/20",
      )}
    >
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {label ?? status.toUpperCase()}
    </span>
  );
}

export function DemoBadge() {
  return (
    <span className="inline-flex items-center rounded-full bg-cream-100 px-2.5 py-0.5 text-xs font-medium text-ink-500 ring-1 ring-inset ring-line-200">
      Demo data
    </span>
  );
}

/* ---------- Form controls ---------- */

interface FieldProps {
  label: string;
  hint?: string;
  children: ReactNode;
}

export function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink-800">
        {label}
      </span>
      {children}
      {hint ? <span className="mt-1.5 block text-xs text-ink-500">{hint}</span> : null}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-line-300 bg-white px-3 py-2 text-sm text-ink-900 placeholder:text-ink-500/60 hover:border-line-300 focus:border-brand-600 focus:outline-none";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(inputClass, props.className)} />;
}

export function Textarea(
  props: React.TextareaHTMLAttributes<HTMLTextAreaElement>,
) {
  return (
    <textarea
      {...props}
      className={clsx(inputClass, "min-h-24 resize-y", props.className)}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={clsx(inputClass, "pr-8", props.className)} />
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors",
        checked ? "bg-brand-700" : "bg-line-300",
      )}
    >
      <span
        aria-hidden
        className={clsx(
          "inline-block size-5 transform rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-5" : "translate-x-0.5",
        )}
        style={{ marginTop: 2 }}
      />
    </button>
  );
}

/* ---------- Empty state ---------- */

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line-300 bg-white px-6 py-14 text-center">
      <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-cream-100 text-ink-500">
        {icon}
      </div>
      <h3 className="font-display text-lg text-ink-900">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-ink-500">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

/* ---------- Confirmation dialog ---------- */

/** Accessible modal for destructive actions. State is owned by the caller;
 * this component is presentational so it stays server-render safe. */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 px-4"
      onMouseDown={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        className="w-full max-w-sm rounded-xl border border-line-200 bg-white p-6 shadow-lg"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 id="confirm-title" className="font-display text-lg text-ink-900">
          {title}
        </h2>
        <p id="confirm-message" className="mt-2 text-sm text-ink-500">
          {message}
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy ? "Working…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Steps indicator ---------- */
export function StepsIndicator({
  steps,
  current,
}: {
  steps: string[];
  current: number;
}) {
  return (
    <ol className="flex items-center gap-1" aria-label="Progress">
      {steps.map((step, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li key={step} className="flex flex-1 items-center gap-1 last:flex-none">
            <div className="flex flex-1 flex-col gap-1.5">
              <span
                className={clsx(
                  "text-xs font-medium",
                  active
                    ? "text-brand-700"
                    : done
                      ? "text-ink-700"
                      : "text-ink-500",
                )}
              >
                {step}
              </span>
              <span
                aria-hidden
                className={clsx(
                  "h-1 rounded-full",
                  done
                    ? "bg-brand-700"
                    : active
                      ? "bg-brand-300"
                      : "bg-line-200",
                )}
              />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
