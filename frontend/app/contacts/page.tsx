import { ContactRound, Plus } from "lucide-react";
import { AppShell } from "@/components/shell";
import { Button, Card, DemoBadge, EmptyState, PageHeader } from "@/components/ui";

/* DEMO DATA — contacts backend is not connected yet. */

export default function ContactsPage() {
  return (
    <AppShell>
      <PageHeader
        title="Contacts"
        subtitle="People your AI employees have spoken with."
        actions={
          <>
            <DemoBadge />
            <Button>
              <Plus size={16} /> Add contact
            </Button>
          </>
        }
      />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-line-200 text-xs uppercase tracking-wider text-ink-500">
                <th scope="col" className="px-5 py-3 font-medium">Name</th>
                <th scope="col" className="px-5 py-3 font-medium">Phone</th>
                <th scope="col" className="px-5 py-3 font-medium">Last call</th>
                <th scope="col" className="px-5 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-200">
              {(
                [
                  ["Priya Sharma", "+91 98200 12345", "Today, 11:42 AM", "Lead"],
                  ["Rahul Mehta", "+91 98111 67890", "Today, 11:18 AM", "Customer"],
                  ["Anita Desai", "+91 98333 24680", "Today, 10:56 AM", "Follow-up"],
                ] as const
              ).map(([name, phone, lastCall, status]) => (
                <tr key={phone} className="transition-colors hover:bg-cream-50">
                  <td className="px-5 py-3.5 font-medium text-ink-900">{name}</td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">{phone}</td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">{lastCall}</td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-ink-700">{status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <div className="mt-6">
        <EmptyState
          icon={<ContactRound size={22} />}
          title="Import your customer list"
          description="Upload a CSV to give your employees context on every caller. Imports are disabled in this demo."
        />
      </div>
    </AppShell>
  );
}
