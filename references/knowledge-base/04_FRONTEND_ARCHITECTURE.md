# Frontend Architecture

## Core Philosophy: Server-First

### React Server Components (RSC)
The frontend architecture is built around React Server Components as the default:
- Data fetching happens on the server
- Components render to HTML before reaching the client
- Client JavaScript is only loaded for interactive components
- Bundle size is minimized automatically

**Reusable Insight:** Use server components as the default. Only mark components as client components when they need interactivity (state, effects, event handlers).

### Next.js App Router
The App Router provides:
- File-based routing with nested layouts
- Server components by default
- Server actions for form submissions
- Streaming and suspense boundaries
- Built-in metadata and SEO

**Reusable Insight:** The App Router's file-based routing maps directly to URL structure. Use nested layouts for shared UI (navigation, sidebars).

## Component Architecture

### Component Hierarchy
```
app-shell.tsx (client component - layout shell)
├── Top navigation bar
├── User display + sign-out
└── Main content area (server components)
    ├── Page components (server)
    │   ├── Data fetching
    │   └── Layout composition
    └── UI components (client when interactive)
        ├── shadcn/ui primitives
        ├── Charts (lazy-loaded)
        └── Admin components
```

### Server vs Client Component Decision Tree
- **Server Component (default):** Data fetching, layout, static content
- **Client Component:** Forms, charts, animations, interactive UI
- **Lazy-loaded Client Component:** Heavy components (charts, tables)

**Reusable Insight:** The boundary between server and client components should be as close to the leaves of the component tree as possible. This minimizes client JavaScript.

### Lazy Loading Strategy
Heavy components (charts, large tables) are dynamically imported:
```typescript
const Chart = dynamic(() => import('./chart'), { ssr: false })
```

**Reusable Insight:** Lazy load anything that:
- Is not visible on initial render
- Requires a large library (charting, data grid)
- Is conditionally rendered
- Is below the fold

## State Management Philosophy

### No Client-Side State Library
The architecture deliberately avoids Redux, Zustand, or similar:
- **Server state:** Fetched in server components, passed as props
- **Form state:** React controlled components
- **Session state:** httpOnly cookies, decoded server-side
- **URL state:** Next.js routing and search params

**Reusable Insight:** With server components, most "state management" problems disappear. Data flows from server to client as props. Only keep client state for UI interactions.

### Server Actions for Mutations
Form submissions use Next.js server actions:
- No API endpoints needed for simple mutations
- Automatic CSRF protection
- Type-safe with TypeScript
- Can call backend API directly

**Reusable Insight:** Server actions eliminate the need for separate API routes for form submissions. Use them for create, update, and delete operations.

## Data Fetching Patterns

### Server Component Data Fetching
```typescript
async function Page() {
  const data = await fetchData()
  return <Component data={data} />
}
```

**Reusable Insight:** Async server components are the simplest data fetching pattern. No loading states, no error boundaries needed for the fetch itself.

### Provider Abstraction Layer
Frontend uses a provider interface (`DashboardDataProvider`) with multiple implementations:
- **RestApiProvider:** Production - calls backend API
- **SampleDataProvider:** Development - deterministic static data
- **ShopmetricsProvider:** Alternative - direct API calls

Selected via environment variable, swapped without UI changes. The contract is fully typed — paginated access goes through `listVisitsPaginated(): Promise<PaginatedVisitsResult>` (typed items, cursors, total count, filter options), and the old fetch-everything `listVisits()` is marked `@deprecated` on the interface itself.

**Reusable Insight:** Define a TypeScript interface for your data layer. Implement it differently for dev, test, and prod. Keep the interface honest: no `Promise<any>` escape hatches, and deprecate old methods *in the contract* so every implementation and caller sees it.

### Resilient Server-Side Fetching
All backend calls funnel through one `backendFetch` helper, which:
- Attaches the Bearer token server-side (the token never reaches client JS)
- Sets `AbortSignal.timeout(30_000)` on every request — a hung backend fails a page in 30s instead of stalling RSC rendering indefinitely
- Defaults to `cache: "no-store"`, with opt-in Next.js tag/revalidate caching per call

**Reusable Insight:** Every server-side fetch in an RSC app is on the critical path of a page render. A single choke-point client with a timeout is the difference between "one slow page" and "the whole app hangs".

### Error Boundaries and Loading States
- Suspense/`loading.tsx` boundaries for loading states
- Segment-level error boundaries: `global-error.tsx` at the root, plus `error.tsx` for the dashboard and admin segments and a dashboard `not-found.tsx`
- Fallback UI matches the design system
- Login errors are differentiated: auth failures (401/403) show "invalid credentials", backend outages show "service unavailable" — never a silent fallback

**Reusable Insight:** Use Suspense for loading states, not manual loading flags. Put an error boundary at every route segment where "this section failed" is a better experience than "the whole app failed" — and never collapse infrastructure errors into user-fault messages.

## Routing and Navigation

### File-Based Routing
- `app/dashboard/page.tsx` -> `/dashboard`
- `app/dashboard/projects/[id]/page.tsx` -> `/dashboard/projects/:id`
- `app/layout.tsx` -> Root layout (shared across all pages)
- `app/dashboard/layout.tsx` -> Dashboard layout (shared across dashboard pages)

**Reusable Insight:** Organize routes by feature, not by type. All files related to a feature live in the same directory.

### Middleware for Auth Routing
Next.js middleware handles the cheap UX layer only:
- Checks token **presence** (not validity) on `/dashboard/*` and `/admin/*`, redirecting to `/login` with a `callbackUrl`
- Redirects already-authenticated users away from `/login`

Token **validity**, role checks, and tenant scoping are enforced server-side on every data fetch (`requireSession` / `requireAdmin` / backend JWT validation) — an expired or revoked token passes the middleware but fails the first real fetch. This is a deliberate trade-off: full JWT validation in Edge middleware adds latency to every request for minimal gain. The post-login `callbackUrl` is sanitized (must start with `/`, `//` rejected) to prevent open redirects.

**Reusable Insight:** Middleware is a UX optimization, not a security boundary. Enforce authorization where data is fetched; treat any URL you redirect to as untrusted input.

## Type Safety

### TypeScript Strict Mode
- No `any` types
- Strict null checks
- Strict function types
- Path aliases (`@/*` -> `src/*`)

**Reusable Insight:** Strict TypeScript catches bugs at compile time. The initial friction pays off in reduced runtime errors.

### Runtime Validation Boundary
Runtime validation currently lives at the **FastAPI boundary** (Pydantic models validate every request body, query param, cursor, and filter). Zod is installed but not yet wired in on the frontend; API response shapes are trusted via the typed provider contract.

**Reusable Insight:** TypeScript catches compile-time errors; runtime validation catches lying data. Validate at least once per trust boundary — if the backend validates rigorously and the frontend is its only client, duplicating every schema in Zod is optional. Add frontend-side schemas when the API is externally versioned or the shapes are hand-mirrored (drift risk).

## Performance Optimization

### Rendering Strategy
- Server components for static/semi-static content
- Client components only for interactivity
- Lazy loading for heavy components
- Streaming for progressive rendering

### Bundle Optimization
- Tree shaking via ES modules
- Code splitting via dynamic imports
- Image optimization via Next.js Image component
- Font optimization via next/font (Space Grotesk + Inter, subsetted)

### Runtime Performance Telemetry
A tiny `<WebVitals />` client component (`useReportWebVitals`) reports Core Web Vitals per navigation; in development it logs metric name, value, and rating to the console.

**Reusable Insight:** Measure before optimizing. Use Next.js bundle analyzer to identify large dependencies, and wire Web Vitals reporting in from day one — the hook costs a few lines and gives you LCP/INP/CLS ground truth.

## Accessibility

### Built-In Accessibility
- Semantic HTML elements
- ARIA labels where needed
- Keyboard navigation support
- Focus management for dialogs and modals

### Reduced Motion
- Respects `prefers-reduced-motion`
- Disables background animations
- Reduces transition durations

**Reusable Insight:** Accessibility is not a feature, it's a requirement. Build it in from the start, not as an afterthought.

## Beyond This Dashboard

Frontend approaches this architecture deliberately avoids — know them so the "no state library" choice stays a decision, not a habit:

### When to Add a Client-Side Data Layer
The RSC-first model breaks down when a view needs **frequent client-side refetching** (polling widgets, live filters that shouldn't trigger navigation, optimistic mutations). That's the moment for **TanStack Query** or **SWR**: request deduplication, stale-while-revalidate on the client, retry, and optimistic updates with rollback. Rule of thumb: URL-state + RSC for anything navigational; a query library only for data that changes *while the user watches*.

### State Libraries, If You Outgrow Props
- **Zustand** — a single small store with selector-based subscriptions; the pragmatic first step beyond `useState` lifting.
- **Jotai** — atomic state; components subscribe to individual atoms, minimizing re-render blast radius (good for dashboards with many independent widgets).
- **Redux Toolkit** — earns its weight only with complex, audited, cross-cutting client state (undo/redo, offline queues).
- **XState** — statecharts for genuinely stateful UI flows (multi-step wizards, connection lifecycles) where boolean-flag soup breaks down.

### Alternative Rendering Architectures
- **Partial Prerendering (PPR)** — Next.js's hybrid: static shell served from the edge with dynamic holes streamed in; the natural evolution of this app's static-layout + dynamic-data pages.
- **Islands architecture (Astro)** — the same "server-first, hydrate only interactive leaves" philosophy taken further; a good fit for read-mostly reporting portals.
- **View Transitions API** — native cross-page animated transitions without a SPA router; progressive enhancement for dashboard navigation.
- **Form state at scale** — React Hook Form (uncontrolled, per-field subscriptions) once forms exceed a handful of controlled inputs; pairs with a schema validator for shared client/server validation.

### Type-Safe API Boundaries Without Hand-Mirroring
This app hand-writes TypeScript types that mirror Pydantic models. Alternatives that remove the drift: generate types from the FastAPI OpenAPI schema (`openapi-typescript`), or use **tRPC**-style end-to-end inference when both ends are TypeScript. The generated-client approach is the highest-leverage upgrade available to this pattern.
