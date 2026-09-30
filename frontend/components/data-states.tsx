import { Button } from "./ui";

/** Shared loading / error / unavailable states for real-data pages. */

export function LoadingState({ label }: { label: string }) {
  return (
    <div
      className="rounded-xl border border-line-200 bg-white px-5 py-10 text-center"
      role="status"
      aria-live="polite"
    >
      <p className="text-sm text-ink-500">Loading {label}…</p>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      className="rounded-xl border border-red-200 bg-red-50/50 px-5 py-10 text-center"
      role="alert"
    >
      <p className="text-sm font-medium text-red-800">
        Couldn&apos;t load this data.
      </p>
      <p className="mx-auto mt-1 max-w-md text-xs text-red-700/80">{message}</p>
      <div className="mt-4">
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    </div>
  );
}

export function Unavailable({ label }: { label: string }) {
  return (
    <p className="text-sm text-ink-500">
      {label}: <span className="font-medium">Not available yet</span>
    </p>
  );
}
