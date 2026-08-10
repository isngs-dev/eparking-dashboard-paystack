# Knowledge Base - Shopmetrics Dashboard Platform

A reusable knowledge base of architectural patterns, design philosophies, and implementation approaches extracted from the Shopmetrics (iSN) Dashboard Platform.

## Purpose

This knowledge base captures **transferable knowledge** - patterns, decisions, and philosophies that can be applied to other projects. It intentionally avoids project-specific details in favor of reusable concepts.

Each file ends with a **"Beyond This Dashboard"** section: patterns and techniques relevant to that file's topic that this system deliberately does *not* use (alternative multi-tenancy models, other RBAC/ABAC/ReBAC approaches, other caching and deployment strategies, …) — so the docs work as a standalone reference when architecting other dashboards.

## Structure

| File | Focus |
|------|-------|
| [01_SYSTEM_DESIGN.md](./01_SYSTEM_DESIGN.md) | Architecture, patterns, and system-level decisions |
| [02_BACKEND_PHILOSOPHY.md](./02_BACKEND_PHILOSOPHY.md) | Backend design principles, data access, security |
| [03_API_SERVICES.md](./03_API_SERVICES.md) | API design, SWR caching, keyset pagination, error handling, rate limiting |
| [04_FRONTEND_ARCHITECTURE.md](./04_FRONTEND_ARCHITECTURE.md) | Frontend patterns, component design, state management |
| [05_UI_DESIGN_SYSTEM.md](./05_UI_DESIGN_SYSTEM.md) | Design language, runtime brand theming, accessibility |
| [06_DATA_PIPELINE.md](./06_DATA_PIPELINE.md) | Ingestion patterns, Celery scheduling, idempotency, cache invalidation |
| [07_SECURITY_PATTERNS.md](./07_SECURITY_PATTERNS.md) | Authentication, JWT lifecycle + revocation, authorization, encryption, hardening (updated after security audit v2) |
| [08_INFRASTRUCTURE.md](./08_INFRASTRUCTURE.md) | Deployment, containerization, observability (marked current-vs-target) |
| [09_TESTING_STRATEGY.md](./09_TESTING_STRATEGY.md) | Testing approaches, coverage philosophy, current gaps |
| [10_DECISION_RECORDS.md](./10_DECISION_RECORDS.md) | ADRs 001–013, including three-tier RBAC, SWR cache, fail-closed rate limiting |
| [RBAC_MODEL.md](./RBAC_MODEL.md) | The three-tier PLATFORM_ADMIN / CLIENT_ADMIN / TENANT_USER model, tenant isolation, alternatives (ABAC/ReBAC) |
| [Backend Components.md](./Backend%20Components.md) | Production-readiness checklist for backend features |
| [frontend_optimization_guide.md](./frontend_optimization_guide.md) | Deep reference on high-performance dashboard frontends |
| [dashboard_layout_frontend.md](./dashboard_layout_frontend.md) | Dashboard UI/layout insights + information-architecture patterns |

## Core Philosophy

This system was built on these foundational principles:

1. **Server-First** - Push logic to the server, minimize client JavaScript
2. **Security by Default** - Every layer assumes hostility
3. **Tenant Isolation** - Multi-tenancy is mandatory, not optional
4. **Repository Abstraction** - Contracts over implementations
5. **Observability** - If you can't measure it, you can't manage it
6. **Graceful Degradation** - Systems should fail predictably (and fail *closed* where security is at stake)
7. **No Silent Fallbacks** - Explicit failures over hidden degradation
