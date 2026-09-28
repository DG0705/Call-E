import Link from "next/link";
import { AppShell } from "@/components/shell";
import { Button } from "@/components/ui";

export default function NotFound() {
  return (
    <AppShell>
      <div className="mx-auto max-w-md py-16 text-center">
        <p className="font-display text-6xl text-brand-700">404</p>
        <h1 className="mt-4 font-display text-2xl text-ink-900">
          This page doesn&apos;t exist
        </h1>
        <p className="mt-2 text-sm text-ink-500">
          The link may be wrong, or the page may have moved.
        </p>
        <div className="mt-6">
          <Link href="/overview">
            <Button>Back to overview</Button>
          </Link>
        </div>
      </div>
    </AppShell>
  );
}
