---
title: Shared Auth RBAC SSO Operator Guide
description: Rollout, validation, and rollback guidance for CCDash shared auth, RBAC, and SSO providers
audience: operators, developers, security
tags: [auth, rbac, sso, rollout, operations]
created: 2026-05-03
updated: 2026-05-03
category: operations
status: active
related: ["shared-auth-rbac-role-matrix.md", "../project_plans/implementation_plans/enhancements/shared-auth-rbac-sso-v1.md"]
---

# Shared Auth RBAC SSO Operator Guide

Use this guide when enabling CCDash auth in hosted API runtimes or keeping local developer no-auth explicit and safe. The current implementation supports local no-auth, static bearer API auth, Clerk JWT/id token validation, and generic OIDC JWT/id token validation. OAuth authorization-code exchange is not implemented yet; do not plan a rollout that depends on CCDash exchanging an OAuth `code` for tokens.

## Runtime Model

Auth provider selection is API-runtime configuration:

| Provider | Select with | Supported current use | Browser SSO status |
| --- | --- | --- | --- |
| Local no-auth | `CCDASH_AUTH_PROVIDER=local` plus `CCDASH_LOCAL_NO_AUTH_ENABLED=true` in hosted API mode | Local/test operator identity; hosted break-glass only behind an external trusted auth boundary | No SSO; returns a local operator session. |
| Static bearer | `CCDASH_AUTH_PROVIDER=static_bearer` | API/CLI-oriented bearer token for `/api/v1/*` | Not full browser SSO. Other hosted routes can still have anonymous fallback behavior. |
| Clerk | `CCDASH_AUTH_PROVIDER=clerk` | Clerk JWT/id token validation for API requests and `/api/auth/callback?id_token=...` | CCDash does not perform Clerk browser redirect. Use the Clerk frontend SDK and send an `id_token` to CCDash. |
| Generic OIDC | `CCDASH_AUTH_PROVIDER=oidc` | OIDC JWT/id token validation and OIDC metadata discovery/JWKS verification | `/api/auth/login/start` can produce a provider URL, but callback with OAuth `code` returns `501`; use an id-token path until code exchange lands. |

Hosted API runtimes use `RoleBindingAuthorizationPolicy`. Local and test runtimes use `PermitAllAuthorizationPolicy`, which allows every backend action. The local identity provider may attach an `owner` membership when `x-ccdash-project-id` is present, but local authorization is still permissive.

## Provider Setup

### Local Developer No-Auth

Use local no-auth for developer machines and tests only:

```bash
export CCDASH_STORAGE_PROFILE=local
export CCDASH_DB_BACKEND=sqlite
export CCDASH_AUTH_PROVIDER=local
export CCDASH_LOCAL_NO_AUTH_ENABLED=true
npm run dev
```

Validate the local session:

```bash
curl -fsS http://localhost:8000/api/auth/metadata | python3 -m json.tool
curl -fsS http://localhost:8000/api/auth/session | python3 -m json.tool
```

Expected: metadata shows `provider: "local"` and session shows `authenticated: true`, `authMode: "local"`, and `localMode: true`.

For hosted API mode, `CCDASH_AUTH_PROVIDER=local` requires `CCDASH_LOCAL_NO_AUTH_ENABLED=true` and emits a hosted no-auth warning. Use that only as a controlled rollback or behind a trusted external authentication boundary.

### Static Bearer

Static bearer is the default provider for `api` runtime when `CCDASH_AUTH_PROVIDER` is unset. Configure a strong secret:

```bash
export CCDASH_AUTH_PROVIDER=static_bearer
export CCDASH_API_BEARER_TOKEN='replace-with-a-long-random-token'
```

Validate the protected `/api/v1` boundary:

```bash
BASE=http://localhost:8000
TOKEN='replace-with-a-long-random-token'

curl -i "$BASE/api/v1/instance"
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/instance" | python3 -m json.tool
```

Expected: the unauthenticated request is rejected for `/api/v1/*`; the bearer request succeeds. Do not treat this as browser SSO. It is best suited to CLI clients, service clients, smoke tests, and API integrations.

### Clerk

Configure Clerk validation secrets on the API service:

```bash
export CCDASH_AUTH_PROVIDER=clerk
export CCDASH_CLERK_PUBLISHABLE_KEY='pk_test_or_live_...'
export CCDASH_CLERK_SECRET_KEY='sk_test_or_live_...'
export CCDASH_CLERK_JWT_KEY='-----BEGIN PUBLIC KEY-----...'
# Optional hardening:
export CCDASH_CLERK_AUTHORIZED_PARTIES='https://ccdash.example.com'
export CCDASH_CLERK_AUDIENCE='ccdash'
```

The current backend validates Clerk JWTs and id tokens. Browser redirect is expected to come from the Clerk frontend SDK; CCDash returns `503` from its own Clerk login redirect helper. After the frontend obtains an id token, submit it to:

```text
/api/auth/callback?state=<state-from-login-start>&id_token=<clerk-id-token>
```

For direct API validation, send the token as a bearer token to a protected route:

```bash
curl -fsS -H "Authorization: Bearer $CLERK_ID_TOKEN" \
  http://localhost:8000/api/sessions?offset=0\&limit=1 | python3 -m json.tool
```

### Generic OIDC

Configure the issuer, client metadata, and JWKS URL:

```bash
export CCDASH_AUTH_PROVIDER=oidc
export CCDASH_OIDC_ISSUER='https://issuer.example.com'
export CCDASH_OIDC_AUDIENCE='ccdash'
export CCDASH_OIDC_CLIENT_ID='ccdash-web'
export CCDASH_OIDC_CLIENT_SECRET='replace-with-client-secret'
export CCDASH_OIDC_CALLBACK_URL='https://ccdash.example.com/api/auth/callback'
export CCDASH_OIDC_JWKS_URL='https://issuer.example.com/.well-known/jwks.json'
```

OIDC bearer/id-token validation is implemented. OAuth authorization-code exchange is not implemented; `/api/auth/callback?code=...` returns `501`. Until that lands, use an id-token callback path or bearer-token API validation:

```bash
curl -fsS -H "Authorization: Bearer $OIDC_ID_TOKEN" \
  http://localhost:8000/api/sessions?offset=0\&limit=1 | python3 -m json.tool
```

## Cookie and Session Behavior

Hosted browser session cookies are signed, HTTP-only cookies. The session cookie defaults are:

| Variable | Default | Notes |
| --- | --- | --- |
| `CCDASH_SESSION_COOKIE_NAME` | `ccdash_session` | Main hosted auth session cookie. The transient state cookie appends `_state`. |
| `CCDASH_SESSION_COOKIE_SECURE` | `true` | Keep `true` behind HTTPS. Set `false` only for local HTTP validation. |
| `CCDASH_SESSION_COOKIE_SAMESITE` | `lax` | Accepts `lax`, `strict`, or `none`; invalid values fall back to `lax`. |
| `CCDASH_SESSION_COOKIE_DOMAIN` | unset | Optional shared cookie domain. |
| `CCDASH_TRUSTED_PROXY_ENABLED` | `false` | Enables proxy-aware hosted auth/session behavior where supported by runtime config. |

Session cookies are signed with the first available secret from Clerk secret key, OIDC client secret, API bearer token, Clerk JWT key, or a local fallback. Hosted sessions currently have a one-hour TTL; auth state cookies have a five-minute TTL.

`/api/auth/session` reads the local or hosted session cookie and returns the principal payload. Protected API routes still build request identity through the configured identity provider, so validate the exact route and client path you intend to operate.

## Bootstrap and Lockout Prevention

Before enabling hosted auth:

- Create the bootstrap enterprise and at least one stable bootstrap admin subject.
- Assign the first admin `EA` at `enterprise:{enterprise_id}`; keep at least two human `EA` subjects after setup.
- Prefer stable provider subject keys over email addresses or display names.
- Keep one break-glass `EA` path that does not depend on a mutable group claim.
- Add replacement admin bindings before removing old bindings.
- Confirm imported role aliases normalize to the canonical roles in [Shared Auth RBAC Role Matrix](shared-auth-rbac-role-matrix.md).

Hosted mode must fail closed when required provider variables are missing. Do not remove local or break-glass access until `/api/auth/session` and a representative protected route pass with the bootstrap admin.

## Staged Rollout Validation

Use a disposable staging stack first:

```bash
COMPOSE="docker compose --env-file deploy/runtime/.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres"
$COMPOSE up --build -d
```

Run the baseline checks:

```bash
BASE=http://localhost:8000

curl -fsS "$BASE/api/health/ready" | python3 -m json.tool
curl -fsS "$BASE/api/auth/metadata" | python3 -m json.tool
curl -fsS "$BASE/api/auth/session" | python3 -m json.tool
```

Expected:

- `/api/health/ready` is ready before auth validation starts.
- `/api/auth/metadata` shows the selected provider and configured metadata.
- `/api/auth/session` shows local authenticated session for local mode, anonymous session before hosted sign-in, or the hosted principal after a successful id-token callback.

Validate a representative protected route. For static bearer:

```bash
curl -i "$BASE/api/v1/instance"
curl -fsS -H "Authorization: Bearer $CCDASH_API_BEARER_TOKEN" \
  "$BASE/api/v1/instance" | python3 -m json.tool
```

For Clerk or OIDC bearer/id-token validation:

```bash
curl -fsS -H "Authorization: Bearer $HOSTED_ID_TOKEN" \
  "$BASE/api/sessions?offset=0&limit=1" | python3 -m json.tool
```

For an admin/RBAC path, use an endpoint whose required permission matches the role you are validating. Examples:

```bash
curl -i -H "Authorization: Bearer $HOSTED_ID_TOKEN" \
  "$BASE/api/pricing/catalog"

curl -i -H "Authorization: Bearer $HOSTED_ID_TOKEN" \
  "$BASE/api/execution/launch/capabilities"
```

Check auth logs and metrics during the rollout:

```bash
$COMPOSE logs api | rg 'auth\.|auth\.request_context|Bearer token|Hosted auth|authorization'
curl -fsS http://localhost:9464/metrics | rg 'ccdash_auth_(login_failures|session_errors|authorization_decisions|issuer_health)_total'
```

Investigate any increase in:

- `ccdash_auth_login_failures_total`
- `ccdash_auth_session_errors_total`
- `ccdash_auth_authorization_decisions_total{decision="denied"...}` when labels are available
- `ccdash_auth_issuer_health_total{status="error"...}` for hosted providers

## Rollback

Rollback should preserve data and change only auth posture.

For a static bearer rollout, restore the previous token or provider env and restart the API:

```bash
export CCDASH_AUTH_PROVIDER=static_bearer
export CCDASH_API_BEARER_TOKEN="$PREVIOUS_CCDASH_API_BEARER_TOKEN"
$COMPOSE up -d api
curl -fsS -H "Authorization: Bearer $CCDASH_API_BEARER_TOKEN" \
  "$BASE/api/v1/instance" | python3 -m json.tool
```

For a Clerk/OIDC rollout that is locking out operators, temporarily return to the last known-good provider or, if an external trusted auth boundary is already enforcing access, use hosted local no-auth as a break-glass step:

```bash
export CCDASH_AUTH_PROVIDER=local
export CCDASH_LOCAL_NO_AUTH_ENABLED=true
$COMPOSE up -d api
curl -fsS "$BASE/api/auth/session" | python3 -m json.tool
```

After access is restored, add or repair `EA` bindings first, validate with the bootstrap admin, then re-enable the hosted provider:

```bash
export CCDASH_AUTH_PROVIDER=oidc
$COMPOSE up -d api
curl -fsS "$BASE/api/auth/metadata" | python3 -m json.tool
curl -fsS -H "Authorization: Bearer $HOSTED_ID_TOKEN" \
  "$BASE/api/sessions?offset=0&limit=1" | python3 -m json.tool
```

Do not keep hosted local no-auth enabled after the incident unless the API remains behind a trusted authentication gateway and that exception is documented.
