# ADR-001: Domain-Scoped Monorepo Architecture

**Status:** Accepted  
**Date:** 2026-03-30  
**Decision Makers:** Team Lead, Principal Engineer

## Context

Nexus Notebook 11 LM requires a modular architecture that supports 15+ domain modules,
async task processing, real-time collaboration, and multi-model AI orchestration.

## Decision

Adopt a **domain-scoped monorepo** with `src/[domain]/[module]` layout where:
- Each module has a single `__init__.py` containing the complete public API
- Modules communicate through explicit imports, not runtime discovery
- Cross-cutting concerns (auth, telemetry, rate-limiting) live in `src/core/`

## Consequences

### Positive
- Clear ownership boundaries per module
- Easy to reason about dependencies
- Simple deployment (single Docker image)
- IDE navigation and refactoring work naturally

### Negative
- Larger monorepo size over time
- All modules must be compatible with same Python version
- Deployment is all-or-nothing (no independent module deploys)

## Alternatives Considered
1. **Microservices**: Rejected — operational overhead too high for team size
2. **Plugin architecture**: Rejected — reduces type safety and IDE support
3. **Framework-based (Django)**: Rejected — too opinionated for our async-heavy workload
