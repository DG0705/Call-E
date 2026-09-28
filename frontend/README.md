# Call-E frontend — premium AI-workforce workspace (Next.js + TypeScript + Tailwind).

## Develop

```sh
cd frontend
cp .env.example .env.local   # optional; defaults to http://localhost:8080
npm install
npm run dev                  # http://localhost:3000
```

## Quality gates

```sh
npm run build    # production build (also typechecks)
npm run lint     # eslint
```

## Architecture

- `app/` — App Router routes (overview, employees, calls, knowledge, contacts,
  analytics, integrations, developer, settings).
- `components/` — `shell.tsx` (sidebar/topbar/app shell), `ui.tsx` (design-system
  primitives: burgundy/cream/ink tokens, buttons, cards, badges, forms).
- `lib/api/` — typed backend client (`client.ts`, `resources.ts`). Base URL from
  `NEXT_PUBLIC_API_BASE_URL`. No `fetch()` calls in components.
- `lib/mock/data.ts` — **demo fixtures only**, each surface labelled “Demo data”.
  Replace `getDemo*` call sites with `lib/api` functions to go live.

No backend services were modified for this milestone. `docker-compose.yml` is
untouched; run the frontend with `npm run dev` alongside the existing stack.
