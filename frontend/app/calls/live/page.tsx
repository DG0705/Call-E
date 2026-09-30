import Link from "next/link";
import { Radio } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Button, EmptyState, PageHeader } from "@/components/ui";

/** No live-call tracking endpoint exists in the backend yet, so this page is
 * an honest empty state — never a fake active call. */

export default function LiveCallsPage() {
  return (
    <AppShell>
      <PageHeader
        title="Live Calls"
        subtitle="Watch active conversations as they happen."
      />
      <EmptyState
        icon={<Radio size={22} />}
        title="No live call tracking yet"
        description="There is no backend endpoint that reports in-progress calls. Place a real call to your inbound number — completed calls appear in call history."
        action={
          <Link href="/calls/history">
            <Button variant="secondary">View call history</Button>
          </Link>
        }
      />
    </AppShell>
  );
}
