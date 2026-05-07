# Guardrails: Planning-Forensics Boundary Extraction v1

## Overview

This document defines what is explicitly **NOT in scope** for the planning-forensics boundary extraction refactor. These guardrails prevent scope creep and clarify the architectural constraints of this work.

## Out of Scope

### 1. No Database Split

Planning and forensics continue to share the same SQLite/PostgreSQL database. No separate databases, schemas, or connection pools are created as part of this refactor.

**Rationale**: Splitting storage is a major database infrastructure change; this refactor focuses on logical separation at the service/query layer only.

### 2. No Service Fork

There is no plan to fork the backend into separate planning and forensics services or processes. Both domains remain in the same FastAPI application, running in the same runtime (local, api, or worker).

**Rationale**: Process-level separation is a deployment architecture change; this refactor is about cleanly separating concerns within a single application.

### 3. No OpenTelemetry Merge-Policy Implementation

OpenTelemetry instrumentation changes related to merging or splitting trace policies are not in scope for this refactor.

**Rationale**: OTel trace-policy changes are a separate observability effort; they can be implemented independently after boundary extraction is complete.

### 4. No Storage Migration

No data migration, table restructuring, or storage format changes are performed as part of this work.

**Rationale**: Existing data structures (sessions, documents, features, links, cache tables) remain unchanged; only the layer above them is reorganized.

### 5. Shared Substrate Remains Unchanged

Plan documents, feature/document/session links, normalized session ingestion, cache/provenance tracking, and live invalidation all continue to use the shared data layer and existing repository contracts.

**Rationale**: The boundary extraction is about query-service organization, not data model restructuring; the foundation stays intact.

## Scope Summary

This refactor **does** separate:
- Query services into planning-specific and forensics-specific intelligences
- REST endpoints and query surfaces by domain concern
- CLI command groups and MCP tool namespaces

This refactor **does not**:
- Split infrastructure (database, services, processes)
- Change data models or storage formats
- Alter observability policies
- Reorganize how data is ingested or normalized
