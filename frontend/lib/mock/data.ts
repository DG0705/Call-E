/** Demo/presentation data for the Call-E workspace.
 *
 * DEMO DATA — every export here is static fixture content used so the UI
 * looks complete before backend integration. Nothing here represents a real
 * backend result. To go live, replace the `getDemo*` call sites with the
 * typed functions in `lib/api/resources.ts`.
 */

export const DEMO_DATA_BADGE = "Demo data" as const;

export interface DemoEmployee {
  id: string;
  name: string;
  description: string;
  role: string;
  status: "live" | "paused" | "draft" | "error";
  calls: number;
  successRate: number;
  avgDuration: string;
  leads: number;
  initials: string;
}

export interface DemoCall {
  id: string;
  date: string;
  time: string;
  employee: string;
  employeeId: string;
  customer: string;
  duration: string;
  durationSeconds: number;
  outcome: string;
  status: "completed" | "in-progress" | "failed" | "missed";
}

export interface DemoTranscriptLine {
  speaker: "ai" | "customer";
  text: string;
  time: string;
}

export const demoMetrics = {
  activeEmployees: 3,
  callsToday: 47,
  successfulConversations: 41,
  leadsCaptured: 12,
};

export const demoEmployees: DemoEmployee[] = [
  {
    id: "kaari-sales",
    name: "Kaari Sales Assistant",
    description: "Handles inbound product enquiries and lead qualification.",
    role: "Sales",
    status: "live",
    calls: 128,
    successRate: 87,
    avgDuration: "3m 42s",
    leads: 34,
    initials: "KS",
  },
  {
    id: "support-riya",
    name: "Support Copilot",
    description: "Answers order questions and routes issues to the team.",
    role: "Customer Support",
    status: "live",
    calls: 96,
    successRate: 91,
    avgDuration: "2m 58s",
    leads: 6,
    initials: "SC",
  },
  {
    id: "frontdesk-ava",
    name: "Frontdesk Ava",
    description: "Greets callers, books appointments and takes messages.",
    role: "Receptionist",
    status: "paused",
    calls: 41,
    successRate: 78,
    avgDuration: "1m 47s",
    leads: 9,
    initials: "FA",
  },
];

export const demoRecentCalls: DemoCall[] = [
  {
    id: "call-9042",
    date: "Today",
    time: "11:42 AM",
    employee: "Kaari Sales Assistant",
    employeeId: "kaari-sales",
    customer: "+91 98200 12345",
    duration: "4m 12s",
    durationSeconds: 252,
    outcome: "Lead captured",
    status: "completed",
  },
  {
    id: "call-9041",
    date: "Today",
    time: "11:18 AM",
    employee: "Support Copilot",
    employeeId: "support-riya",
    customer: "+91 98111 67890",
    duration: "2m 47s",
    durationSeconds: 167,
    outcome: "Resolved",
    status: "completed",
  },
  {
    id: "call-9040",
    date: "Today",
    time: "10:56 AM",
    employee: "Kaari Sales Assistant",
    employeeId: "kaari-sales",
    customer: "+91 98333 24680",
    duration: "3m 05s",
    durationSeconds: 185,
    outcome: "Follow-up",
    status: "completed",
  },
  {
    id: "call-9039",
    date: "Today",
    time: "10:31 AM",
    employee: "Frontdesk Ava",
    employeeId: "frontdesk-ava",
    customer: "+91 98444 13579",
    duration: "1m 22s",
    durationSeconds: 82,
    outcome: "Appointment booked",
    status: "completed",
  },
  {
    id: "call-9038",
    date: "Yesterday",
    time: "6:04 PM",
    employee: "Kaari Sales Assistant",
    employeeId: "kaari-sales",
    customer: "+91 98555 97531",
    duration: "0m 41s",
    durationSeconds: 41,
    outcome: "Missed",
    status: "missed",
  },
];

export const demoLiveTranscript: DemoTranscriptLine[] = [
  { speaker: "ai", text: "Sure. How many planters are you looking for?", time: "00:12" },
  { speaker: "customer", text: "Around four.", time: "00:19" },
  { speaker: "ai", text: "Got it. What size are you looking for?", time: "00:24" },
  { speaker: "customer", text: "About eighteen inches, for the balcony.", time: "00:31" },
  { speaker: "ai", text: "Okay. Are they for indoors or outdoors?", time: "00:38" },
];

export const demoCallTranscript: DemoTranscriptLine[] = [
  ...demoLiveTranscript,
  { speaker: "customer", text: "Outdoors.", time: "00:44" },
  {
    speaker: "ai",
    text: "The Aqua 20 could work well for the size you mentioned. Would you like me to tell you the price?",
    time: "00:51",
  },
];

export const demoKnowledgeSources = [
  { id: "kb-1", name: "Kaari product catalog 2026.pdf", kind: "document", items: 48, updated: "2 days ago" },
  { id: "kb-2", name: "kaariplanters.com", kind: "website", items: 132, updated: "5 hours ago" },
  { id: "kb-3", name: "Pricing & discount policy", kind: "text", items: 6, updated: "1 week ago" },
];

export const demoActivity = [
  { label: "Mon", calls: 18 },
  { label: "Tue", calls: 26 },
  { label: "Wed", calls: 31 },
  { label: "Thu", calls: 24 },
  { label: "Fri", calls: 39 },
  { label: "Sat", calls: 47 },
  { label: "Sun", calls: 29 },
];

export function getDemoEmployees(): DemoEmployee[] {
  return demoEmployees;
}

export function getDemoEmployee(id: string): DemoEmployee | undefined {
  return demoEmployees.find((employee) => employee.id === id);
}

export function getDemoCalls(): DemoCall[] {
  return demoRecentCalls;
}

export function getDemoCall(id: string): DemoCall | undefined {
  return demoRecentCalls.find((call) => call.id === id);
}
