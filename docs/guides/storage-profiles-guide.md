# CCDash Storage Profiles Guide

Updated: 2026-03-27

## Purpose

CCDash now treats storage as an explicit operator-facing profile instead of only a low-level database toggle.

| Storage profile | Primary database | Source of truth | Typical deployment |
| --- | --- | --- | --- |
| `local` | SQLite | Filesystem-derived artifacts plus local cache metadata | Desktop and single-user local-first |
| `enterprise` | Postgres | Postgres for canonical app state, filesystem as ingestion only | Hosted API + worker deployments |

`CCDASH_DB_BACKEND` remains a compatibility setting, but `CCDASH_STORAGE_PROFILE` is the architectural control point.

## Configuration

### Local

- Use `CCDASH_STORAGE_PROFILE=local` or leave it unset.
- Keep `CCDASH_DB_BACKEND=sqlite`.
- Filesystem watch and sync remain first-class runtime behavior.

### Enterprise

- Set `CCDASH_STORAGE_PROFILE=enterprise`.
- Set `CCDASH_DB_BACKEND=postgres`.
- Set `CCDASH_DATABASE_URL`.
- Treat filesystem access as an ingestion concern, not an API assumption.

## Shared Postgres Contract

Shared Postgres is allowed only for the `enterprise` storage profile.

- `CCDASH_STORAGE_SHARED_POSTGRES=true` enables the shared-instance posture.
- `CCDASH_STORAGE_ISOLATION_MODE=schema` means CCDash owns a dedicated schema boundary.
- `CCDASH_STORAGE_ISOLATION_MODE=tenant` means tenant isolation must be enforced by the hosted deployment contract.
- `CCDASH_STORAGE_ISOLATION_MODE=dedicated` is valid only when the Postgres instance is CCDash-owned.
- Cross-application table coupling is not allowed even in shared infrastructure.

## Runtime Mapping

Runtime profiles and storage profiles are related but distinct:

| Runtime profile | Recommended storage profile | Notes |
| --- | --- | --- |
| `local` | `local` | HTTP + watcher + sync + in-process jobs |
| `api` | `enterprise` | Stateless HTTP runtime without incidental watcher work |
| `worker` | `enterprise` | Background sync, refresh, and scheduled jobs |
| `test` | `local` | Minimal runtime with background work disabled |

The `/api/health` payload reports the resolved storage profile, backend, shared-Postgres posture, isolation mode, schema, and canonical session-store mode so operators can verify the runtime contract quickly.
