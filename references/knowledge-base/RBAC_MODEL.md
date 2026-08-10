# RBAC Model - Role-Based Access Control

**Version:** 2.0
**Last Updated:** 2026-07-11
**Status:** PRODUCTION READY (three-tier model, Sprint 07b + security audit v2)

---

## Overview

The iSN / Shopmetrics Dashboard Platform implements a strict multi-tenant RBAC model to ensure:
1. **Tenant Isolation** - Clients can only access their own data
2. **Least Privilege** - Users have minimum necessary permissions
3. **Single Platform Admin** - Keep the count of global administrator accounts at one
4. **Audit Trail** - Clear separation of platform, company-admin, and client actions

The hierarchy is: **Company → Tenants → Projects → Visits/Photos/Metrics.**
A company (e.g. an agency or brand group) owns one or more tenants; every data row below a tenant carries its `tenant_id`.

---

## User Roles (three-tier)

Legacy role strings are migrated transparently at JWT decode time and when reading DB rows:
`ADMIN → PLATFORM_ADMIN`, `CLIENT → TENANT_USER` (see `resolve_role()` in `services/common/models.py`).

### PLATFORM_ADMIN

**Purpose:** System-wide administration — platform settings, companies, tenants, provider connections, refresh dispatch.

**Permissions:**
| Permission | Granted | Notes |
|------------|---------|-------|
| Access all companies/tenants/projects | ✅ | Explicit `tenant_scope(claims) is None` cross-tenant path |
| Platform settings (`/admin/settings/*` admin-only keys) | ✅ | site_title, logo_text, footer_text, support_* |
| Create/update companies and tenants | ✅ | PLATFORM_ADMIN only |
| Provider connections (Shopmetrics credentials) | ✅ (write) | Writes are PLATFORM_ADMIN only; secrets never echoed back |
| Trigger data refresh / toggle scheduled refresh | ✅ | Dispatches Celery tasks |
| Create users of any role | ✅ | Including other PLATFORM_ADMINs (discouraged — see lifecycle) |

**JWT Claims:**
```json
{
  "sub": "user_admin",
  "email": "admin@demo.local",
  "role": "PLATFORM_ADMIN",
  "tenant_id": null,
  "company_id": null,
  "tenant_ids": [],
  "project_ids": [],
  "jti": "…", "iss": "mss-dashboard-api", "iat": 0, "exp": 0
}
```

### CLIENT_ADMIN

**Purpose:** Company-scoped administration — manages the users, projects, and settings of the tenants belonging to one company, without any platform-wide power.

**Required claims:** `company_id` and a non-empty `tenant_ids` array. A CLIENT_ADMIN token missing either is **rejected at decode time**.

**Permissions:**
| Permission | Granted | Notes |
|------------|---------|-------|
| List/manage tenants in `tenant_ids` | ✅ | Every tenant-scoped admin endpoint calls `_assert_company_access_to_tenant` |
| List/manage users of those tenants | ✅ | `list_users_for_tenants(claims.tenant_ids)` |
| Create/update users | ✅ (scoped) | Cannot create or assign `PLATFORM_ADMIN`; assigned tenants must be within own `tenant_ids` |
| Issue password-reset tokens | ✅ (scoped) | Only for users of accessible tenants |
| Project metadata, photo-slot labels, metrics | ✅ (scoped) | Via `_assert_company_access_to_project` |
| View run logs | ✅ (scoped) | `list_run_logs_for_tenants` |
| Read scheduled-refresh status | ✅ (scoped) | Tenant access check added in audit fix NEW-7 |
| Platform settings writes, provider connections, refresh dispatch, companies | ❌ | PLATFORM_ADMIN only |

**JWT Claims:**
```json
{
  "sub": "user_agency_admin",
  "role": "CLIENT_ADMIN",
  "tenant_id": null,
  "company_id": "company_agency",
  "tenant_ids": ["tenant_labatt", "tenant_other"],
  "project_ids": []
}
```

### TENANT_USER

**Purpose:** Read-only dashboard access, scoped to a single tenant and an explicit project list.

**Required claims:** `tenant_id` (token rejected at decode without it) and `project_ids`.

**Permissions:**
| Permission | Granted | Notes |
|------------|---------|-------|
| Access own tenant's assigned projects | ✅ | Must match `tenant_id` **and** be in `project_ids` |
| Dashboard data (summary, visits, photos) | ✅ | Through tenant-scoped repository queries |
| Appearance settings (read) | ✅ | brand_color, default_theme, date_format only |
| Admin endpoints | ❌ | 403 via route guards |

**JWT Claims:**
```json
{
  "sub": "user_client",
  "role": "TENANT_USER",
  "tenant_id": "tenant_labatt",
  "company_id": null,
  "tenant_ids": [],
  "project_ids": ["project_messi_flying_fish"]
}
```

---

## Access Control Logic

### Backend (canonical enforcement)

```python
# services/common/tenancy.py
def can_access_project(claims, project):
    if claims.role == Role.PLATFORM_ADMIN:
        return True
    if claims.role == Role.CLIENT_ADMIN:
        return project.tenant_id in claims.tenant_ids
    if claims.role == Role.TENANT_USER:
        return (
            claims.tenant_id is not None
            and project.tenant_id == claims.tenant_id
            and project.id in claims.project_ids
        )
    return False

def tenant_scope(claims) -> list[str] | None:
    """None = unrestricted (PLATFORM_ADMIN). A list scopes lookups; [] = no access."""
```

Route guards run as FastAPI dependencies:
- `require_platform_admin` — settings writes, companies, connections, refresh
- `require_client_admin_or_above` — company-scoped admin operations (always paired with `_assert_company_access_to_tenant` / `_assert_company_access_to_project` on the specific resource)

Project lookups use the **composite key** `(tenant_id, project_id)` — two tenants sharing a `project_id` can never cross-resolve (regression-tested in `backend_tests/test_get_project_scoped.py`).

**Authorization runs before cache reads** in the project routes, so a Redis cache hit can never serve an unauthorized project.

### Frontend (defense in depth — `src/server/rbac.ts`)

```typescript
export async function requireAdmin() {        // PLATFORM_ADMIN only
export async function requireAdminOrAbove()   // PLATFORM_ADMIN | CLIENT_ADMIN

// listVisibleProjects():
if (role === "PLATFORM_ADMIN") return projects;
if (role === "CLIENT_ADMIN")  return projects.filter(p => tenantIds.includes(p.clientSlug));
return projects.filter(p => p.clientSlug === clientId);  // TENANT_USER
```

`assertProjectAccess(projectId)` delegates to the backend with a single `GET /projects/{id}` — the backend derives tenant scope from verified JWT claims; the frontend never re-derives authorization from client data. On failure it redirects to `/dashboard`.

The JWT lives in an **httpOnly cookie**; the Next.js server layer forwards it as a Bearer header. Browser JavaScript never sees the token.

---

## Tenant Isolation

### Data Scoping

Every dashboard data row is scoped to a tenant:

```sql
dashboard.companies (company_id PK)
dashboard.tenants  (tenant_id PK, company_id FK)
dashboard.projects (tenant_id, project_id PK)
dashboard.visits   (tenant_id, project_id, survey_id PK)
dashboard.visit_photos (tenant_id, project_id, survey_id, kind, url PK)
dashboard.project_metrics (tenant_id, project_id, key PK)
dashboard.users    (user_id PK, tenant_id, company_id, tenant_ids, role, project_ids)
```

### Query Enforcement

- `tenant_id` comes **only** from verified JWT claims — never from query strings, request bodies, route params, or headers (red line #1)
- Every repository method takes claims or an explicit tenant scope and filters on it
- Cache keys are tenant-namespaced (`t:{tenant_id}:p:{project_id}:…`) and tenant-wide invalidation uses per-tenant key-tracking SETs
- `tenant_id` is established at ingestion time and is immutable
- Client-facing responses strip internal fields (`to_public_dict` removes `hashed_password`; `to_client_visit_dict` removes `tenant_id`/`project_id`)

---

## Security Boundaries

### Backend API (primary boundary)

1. Extract JWT from `Authorization: Bearer <token>`
2. Decode with pinned HS256, validate issuer/expiry/(audience), check the Redis JTI blacklist (revoked tokens rejected)
3. Validate role-specific claims (TENANT_USER needs `tenant_id`; CLIENT_ADMIN needs `company_id` + `tenant_ids`)
4. Role guard → per-resource tenant/project assertion → tenant-scoped query
5. Never trust client-provided tenant identifiers

### Frontend (defense in depth)

- Next.js middleware checks token **presence** only (UX-layer redirect to login); validity and authorization are always re-checked server-side per fetch
- Server components fetch with the token server-side; only rendered data reaches the client
- Admin pages call `requireAdmin`/`requireAdminOrAbove` before rendering

---

## User Lifecycle

### Creating a User (admin panel or API)

1. `POST /admin/users` with email, name, role, tenant/project assignment, password (min 8 chars, Pydantic-validated)
2. Server-side validation: role must be in the enum; the tenant must exist; every `project_id` must belong to that tenant (cross-tenant assignment rejected with 422)
3. CLIENT_ADMIN callers: cannot create PLATFORM_ADMINs; assigned tenant(s) must be within their own `tenant_ids`; `company_id` is stamped from *their* claims, never from the request
4. Duplicate email → 409

### Password Reset (admin-issued)

1. Admin (scoped) calls `POST /admin/users/{id}/password-reset`; receives the raw one-time token (1h TTL) exactly once and relays it out-of-band
2. Only the PBKDF2 hash of the token is stored; `tenant_id` is derived server-side from user metadata
3. User redeems at the public endpoint — response is generic for all outcomes, timing is equalized for unknown emails, and consumption is atomic (`AND consumed_at IS NULL`)

### PLATFORM_ADMIN accounts

**⚠️ Keep exactly one.** If a second is ever required: created by the existing admin, explicitly approved, temporary, deleted after use. Prefer CLIENT_ADMIN with broad `tenant_ids` for delegated administration — that is what the role exists for.

---

## Testing RBAC

### Automated (current)

- `backend_tests/test_tenancy.py` — role scoping matrix for `can_access_project` / `tenant_scope`
- `backend_tests/test_get_project_scoped.py` — composite-key cross-tenant leak regression
- `backend_tests/test_security.py` — JWT claim validation, role migration
- `tests/rbac.test.ts` — frontend role filtering

### Manual Testing Checklist

- [ ] PLATFORM_ADMIN login → sees all projects, all admin pages
- [ ] CLIENT_ADMIN login → sees only own company's tenants/users/projects; cannot open platform settings or connections
- [ ] CLIENT_ADMIN cannot create a PLATFORM_ADMIN user (403)
- [ ] TENANT_USER login → sees only assigned projects; `/admin/*` returns 403
- [ ] TENANT_USER of tenant A requesting a tenant-B project → 403/404, never data
- [ ] Legacy `ADMIN`/`CLIENT` tokens still resolve to the migrated roles
- [ ] Logout revokes the token (subsequent API call with the old token → 401)

---

## Migration History

### 2026-05-29: RBAC Cleanup (Phase 5.1)
Seed script created 10 test admin accounts, violating the single-admin principle. Cleanup deleted them; only one ADMIN remained.

### Sprint 07b: Three-Tier Model
Introduced companies, the CLIENT_ADMIN role, `company_id`/`tenant_ids` JWT claims, `tenant_scope()`, and the legacy-role migration map. `require_admin` remains as a backward-compat alias for `require_platform_admin`.

### 2026-07 Security Audit v2 (RBAC-relevant fixes)
- Scheduled-refresh GET gained the missing `_assert_company_access_to_tenant` check (NEW-7)
- Logout now actually revokes the JWT server-side (NEW-2)
- Password minimum length enforced on all create/update/reset paths (NEW-3)
- Composite-key project lookup regression test added

---

## Future Enhancements

### Planned
1. **Project-Level Roles** - viewer/editor per project
2. **Audit Logging** - track all admin actions for compliance
3. **Session Management** - admin can revoke user sessions (the JTI blacklist provides the primitive)
4. **MFA Support** - two-factor for admin accounts

### Not Planned (v1)
- SSO integration (SAML/OAuth), LDAP/AD sync, custom permission sets, time-based access restrictions

---

## Beyond This Dashboard

Authorization models beyond three-tier RBAC, for when the next system's requirements don't fit roles:

- **ABAC (Attribute-Based Access Control):** decisions computed from attributes of the user, resource, action, and environment ("managers may approve expenses < $5k in their own department during business hours"). Use when rules are conditional and numerous; roles explode combinatorially trying to express them. XACML is the heavyweight standard; policy engines (below) are the practical route.
- **ReBAC (Relationship-Based Access Control):** permissions derived from a graph of relationships — Google Zanzibar's model (`user U is viewer of doc D because U is member of group G which is editor of folder F`). Implementations: SpiceDB, OpenFGA, Ory Keto. This dashboard's Company → Tenant → Project chain is already a small ReBAC graph hand-coded as claim arrays; a relationship store becomes worth it when the hierarchy deepens or sharing gets ad hoc.
- **Policy engines:** OPA/Rego, AWS Cedar, or Casbin externalize authorization into declarative, testable policy separate from application code — valuable once multiple services must enforce identical rules, or when policy changes shouldn't require deploys.
- **Postgres Row-Level Security:** `CREATE POLICY` makes the database itself refuse cross-tenant rows — a safety net under application-level scoping. Caveat: session-based (`SET app.tenant_id`) RLS conflicts with transaction-mode PgBouncer; workable with per-transaction `set_config()`.
- **Claims freshness problem:** baking `tenant_ids`/`project_ids` into a 1-hour JWT means revoking a user's project access takes up to an hour. Mitigations, in increasing cost: shorter tokens + refresh rotation; a claims-version check against Redis per request; or moving membership lookups server-side entirely (claims carry only identity).
- **Permission caching:** when authorization requires lookups (ReBAC/DB-backed), cache *decisions* with short TTLs and invalidate on membership change — the same SWR + set-invalidation machinery this dashboard uses for data works for permissions.
- **Scoped/least-privilege tokens:** OAuth2 scopes or macaroon-style attenuation let a token carry less power than its user (e.g. a read-only export token) — useful for API keys, webhooks, and service-to-service calls.

---

## References

- Backend guards: `services/common/tenancy.py`, `services/api/routes/admin.py`
- Roles & claims: `services/common/models.py`, `services/common/security.py`
- Repository scoping: `services/common/postgres_repository.py`
- Frontend RBAC: `src/server/rbac.ts`
- Database Schema: `services/ingestion/dashboard_schema.sql`, `services/ingestion/migrations/`
- Rules: `.claude/rules/tenant-isolation.md`

---

**End of Document**
