# Testing Strategy

## Testing Philosophy

### Test Pyramid
```
        /\
       /  \      E2E Tests (few)
      /----\
     /      \    Integration Tests (some)
    /--------\
   /          \  Unit Tests (many)
  /------------\
```

**Reusable Insight:** Most tests should be unit tests. They're fast, reliable, and cheap. Integration tests verify boundaries. E2E tests verify the whole system.

### Test Categories
- **Unit tests:** Individual functions and classes
- **Integration tests:** Component interactions
- **Contract tests:** Interface guarantees
- **Smoke tests:** Basic system health

## Backend Testing (pytest)

### Test Organization
```
backend_tests/
├── test_security.py            # JWT, password hashing
├── test_tenancy.py             # Multi-tenant isolation / role scoping
├── test_get_project_scoped.py  # Composite (tenant_id, project_id) lookup — cross-tenant leak regression
├── test_visits_pagination.py   # Keyset pagination semantics + cursor codec
├── test_transform.py           # Data transformation
├── test_rate_limiter.py        # Rate limiting
├── test_secrets.py             # AES-256-GCM encrypt/decrypt
└── test_campaigns.py           # Campaign config
```

**Reusable Insight:** Organize tests by feature, not by file. All tests for a feature live together — and when a security bug is fixed (like the cross-tenant project lookup), pin it with a dedicated regression test file.

### Fixtures and Mocks
- Mock external API calls
- InMemory repository as the test double for the repository Protocol (it deliberately mirrors the Postgres keyset-pagination semantics, so route-layer logic is testable without a database)
- Factory/seed helpers for test data
- Async repository calls are driven via `asyncio.run()` inside plain sync tests (no pytest-asyncio dependency in this environment)

**Reusable Insight:** A faithful in-memory implementation of your data-layer contract is the highest-leverage test fixture you can build — it makes every layer above the repository testable in milliseconds.

### Known Gaps (current)
- Zero tests against the real `postgres_repository.py` (the InMemory twin is tested; SQL itself is not)
- No HTTP-level two-tenant isolation tests (the RBAC matrix is unit-tested, not exercised through FastAPI)
- Ingestion idempotency (UPSERT re-run safety) untested
- No CI pipeline — verification gates are run manually (see below)

**Reusable Insight:** Test coverage is not 100% coverage. It's testing the right things. Focus on critical paths and edge cases — and keep an honest, current list of what is *not* tested.

## Frontend Testing (Vitest)

### Test Organization
```
tests/
├── rbac.test.ts               # Role-based access control
├── seed-parity.test.ts        # Frozen sample-data baseline (436 visits, dates, distributions)
├── provider-contract.test.ts  # Provider interface contracts
├── active-window.test.ts      # Date-window logic
├── cascading-filters.test.ts  # Filter interaction logic
└── chart-helpers.test.ts      # Chart data shaping
```

**Reusable Insight:** Frontend tests should focus on behavior, not implementation. Test what the user sees, not how it's built.

### Testing Approach
- Node environment for server component tests
- Provider contract tests for interface guarantees
- Data parity tests for consistency

**Reusable Insight:** Test the contracts between layers. If the provider interface is tested, the implementation can change safely.

## Test Data Management

### Factory Functions
- Deterministic test data
- Configurable parameters
- Realistic values
- No external dependencies

**Reusable Insight:** Test data should be generated, not hardcoded. Factories make it easy to create variations.

### Seed Data
- Baseline data for parity tests
- Known quantities for assertions
- Version-controlled
- Regenerated when schema changes

**Reusable Insight:** Seed data is documentation. It shows what valid data looks like.

## Continuous Integration

### Verification Gates (currently run manually — no CI pipeline exists yet)
1. Frontend: `npx tsc --noEmit` && `npm run lint` && `npm test` (Vitest)
2. Backend: `python -m pytest backend_tests -v` (inside the project conda env)

### Target CI Pipeline
1. Lint and type check
2. Unit tests
3. Integration tests
4. Build Docker images
5. Smoke tests against built images

**Reusable Insight:** CI should catch problems before they reach production. Fail fast, fail loud. Until CI exists, write the gates down and run them ritually — an undocumented manual gate is the one that gets skipped.

### Test Execution
- Parallel test execution
- Isolated test databases
- Clean state between tests
- Timeout protection

**Reusable Insight:** Tests should be fast and reliable. Slow tests get skipped. Flaky tests get fixed or deleted.

## Testing Anti-Patterns

### What to Avoid
- Testing implementation details
- Testing framework behavior
- Over-mocking (testing mocks, not code)
- Brittle tests (break on refactoring)
- Slow tests (take minutes to run)

**Reusable Insight:** A test that breaks on refactoring is testing implementation, not behavior. Good tests survive refactoring.

### What to Test
- Public interfaces
- Edge cases
- Error handling
- Business rules
- Integration points

**Reusable Insight:** Test behavior, not implementation. Test boundaries, not internals. Test what matters.

## Beyond This Dashboard

Testing techniques this suite doesn't use yet, worth reaching for on the next system:

- **Testcontainers for the real database:** the biggest known gap here (untested SQL) is exactly what Testcontainers solves — spin up a throwaway Postgres per test session, apply the schema, and run the *Postgres* repository against it. Contract-style: run the same test suite against both InMemory and Postgres implementations to prove they agree.
- **Property-based testing:** Hypothesis (Python) / fast-check (TS) generate adversarial inputs. Ideal targets in a codebase like this: the cursor codec (any decode(encode(x)) round-trips; malformed input always 422s), password hash verify, and filter parsing.
- **Schema-driven API fuzzing:** Schemathesis reads the FastAPI OpenAPI schema and fuzzes every endpoint for 500s and contract violations — near-zero-cost coverage of the validation boundary.
- **HTTP-level authorization matrix tests:** a parametrized table of (role, endpoint, expected status) run through FastAPI's `TestClient` catches the class of bug the audit found (a GET missing its tenant check) mechanically.
- **Consumer-driven contract tests (Pact):** when frontend and backend deploy independently, Pact-style contracts replace hand-mirrored types as the drift detector.
- **Mutation testing:** mutmut / Stryker flip operators in your code and check that tests fail — the honest measure of suite strength, run occasionally rather than per-commit.
- **Load testing:** k6 or Locust against the paginated endpoints with realistic tenant fan-out, asserting p95 latency and cache-hit-rate expectations; this is how you validate the SWR + PgBouncer sizing story before users do.
- **Flake quarantine policy:** a tagged quarantine lane plus an SLA ("fix or delete within a week") keeps flaky tests from training the team to ignore red.
