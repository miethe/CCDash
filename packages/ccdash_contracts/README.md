# `ccdash-contracts`

Shared Pydantic contract package for CCDash client API `v1`.

This package is the wire-contract boundary between the CCDash server and the standalone CLI. It contains the public DTOs and envelope models that both sides should agree on for `/api/v1` payloads.

## Purpose

- Keep client-visible DTO ownership out of transport-specific code.
- Give the standalone CLI a stable typed dependency instead of importing backend internals.
- Reduce drift between server response models and client parsing logic.

## Versioning Strategy

- `v1` models in this package define the public compatibility contract for the current standalone CLI.
- Additive, backwards-compatible fields should be preferred within `v1`.
- Breaking wire changes should ship behind a new API/package contract version instead of mutating existing `v1` semantics in place.

## Ownership

- Owns public client-facing DTOs and envelopes under `src/ccdash_contracts/`.
- Does not own backend-only service models, repositories, or CLI formatting concerns.
- Some richer backend router payloads still use thin compatibility DTOs until their nested shapes are fully converged into this package.
- Changes here should be coordinated with both the server API and the standalone CLI when they affect serialized payloads.

## What It Exports

- Envelope types: `ClientV1Envelope`, `ClientV1PaginatedEnvelope`, `ClientV1ErrorEnvelope`
- Envelope metadata: `ClientV1Meta`, `ClientV1PaginatedMeta`, `ClientV1ErrorDetail`
- Shared DTOs: `InstanceMetaDTO`, `FeatureSummaryDTO`, `FeatureSessionsDTO`, `FeatureDocumentsDTO`, `SessionFamilyDTO`, `SessionRef`, `DocumentRef`

## Usage

From the standalone CLI:

```python
from ccdash_contracts.envelopes import ClientV1ErrorEnvelope
from ccdash_contracts.models import InstanceMetaDTO
```

From the server:

```python
from ccdash_contracts.envelopes import ClientV1Envelope
from ccdash_contracts.models import FeatureSummaryDTO, InstanceMetaDTO
```

## Guidance

- Treat these models as the public `/api/v1` contract.
- Prefer adding or evolving shared DTOs here instead of recreating equivalent wire models in the server or CLI packages.
- If a server payload cannot use a shared DTO yet, keep the compatibility layer thin and document why.
- Keep package documentation and downstream docs aligned when new public fields or envelope semantics ship.
