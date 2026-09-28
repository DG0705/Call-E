"use client";

import { useState } from "react";
import { AppShell } from "@/components/shell";
import { Card, DemoBadge, PageHeader, SectionHeading } from "@/components/ui";
import { clsx } from "clsx";

/* Static documentation content — no live backend calls. */

type Language = "cURL" | "Python" | "JavaScript";

const SNIPPETS: { title: string; method: string; path: string; snippets: Record<Language, string> }[] = [
  {
    title: "Create an AI employee",
    method: "POST",
    path: "/api/v1/agents",
    snippets: {
      cURL: `curl -X POST "$BASE_URL/api/v1/agents" \\
  -H "Authorization: Bearer $CALL_E_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"name":"Sarah","role":"Sales"}'`,
      Python: `import os, requests

response = requests.post(
    f"{os.environ["BASE_URL"]}/api/v1/agents",
    headers={"Authorization": f"Bearer {os.environ["CALL_E_KEY"]}"},
    json={"name": "Sarah", "role": "Sales"},
)
response.raise_for_status()`,
      JavaScript: `const response = await fetch(\`\${process.env.BASE_URL}/api/v1/agents\`, {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.CALL_E_KEY}\`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ name: "Sarah", role: "Sales" }),
});`,
    },
  },
  {
    title: "List calls",
    method: "GET",
    path: "/api/v1/calls",
    snippets: {
      cURL: `curl "$BASE_URL/api/v1/calls" \\
  -H "Authorization: Bearer $CALL_E_KEY"`,
      Python: `import os, requests

calls = requests.get(
    f"{os.environ["BASE_URL"]}/api/v1/calls",
    headers={"Authorization": f"Bearer {os.environ["CALL_E_KEY"]}"},
).json()`,
      JavaScript: `const calls = await fetch(\`\${process.env.BASE_URL}/api/v1/calls\`, {
  headers: { Authorization: \`Bearer \${process.env.CALL_E_KEY}\` },
}).then((r) => r.json());`,
    },
  },
  {
    title: "Get one employee",
    method: "GET",
    path: "/api/v1/agents/:id",
    snippets: {
      cURL: `curl "$BASE_URL/api/v1/agents/kaari-sales" \\
  -H "Authorization: Bearer $CALL_E_KEY"`,
      Python: `import os, requests

agent = requests.get(
    f"{os.environ["BASE_URL"]}/api/v1/agents/kaari-sales",
    headers={"Authorization": f"Bearer {os.environ["CALL_E_KEY"]}"},
).json()`,
      JavaScript: `const agent = await fetch(
  \`\${process.env.BASE_URL}/api/v1/agents/kaari-sales\`,
  { headers: { Authorization: \`Bearer \${process.env.CALL_E_KEY}\` } },
).then((r) => r.json());`,
    },
  },
];

const LANGUAGES: Language[] = ["cURL", "Python", "JavaScript"];

export default function ApiDocsPage() {
  const [language, setLanguage] = useState<Language>("cURL");

  return (
    <AppShell>
      <PageHeader
        title="API Docs"
        subtitle="Full programmatic control over employees, calls and knowledge."
        actions={<DemoBadge />}
      />
      <div className="mb-6 flex gap-1 rounded-lg border border-line-200 bg-white p-1" role="tablist" aria-label="Language">
        {LANGUAGES.map((option) => (
          <button
            key={option}
            type="button"
            role="tab"
            aria-selected={language === option}
            onClick={() => setLanguage(option)}
            className={clsx(
              "cursor-pointer rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
              language === option
                ? "bg-brand-700 text-white"
                : "text-ink-600 hover:bg-cream-100",
            )}
          >
            {option}
          </button>
        ))}
      </div>
      <div className="space-y-6">
        {SNIPPETS.map((snippet) => (
          <section key={snippet.path}>
            <SectionHeading title={snippet.title} />
            <Card className="overflow-hidden">
              <div className="flex items-center gap-2 border-b border-line-200 bg-cream-50 px-5 py-2.5 font-mono text-xs">
                <span className="font-semibold text-brand-700">{snippet.method}</span>
                <span className="text-ink-700">{snippet.path}</span>
              </div>
              <pre className="overflow-x-auto bg-ink-900 p-5 text-[13px] leading-relaxed text-stone-100">
                <code>{snippet.snippets[language]}</code>
              </pre>
            </Card>
          </section>
        ))}
      </div>
    </AppShell>
  );
}
