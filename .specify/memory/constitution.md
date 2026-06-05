<!--
Sync Impact Report
==================
Version change: (uninitialized template) → 1.0.0
Rationale: Initial ratification — first concrete constitution for the flowbio client library.

Principles defined (7):
  I.   Test-First Development (NON-NEGOTIABLE)
  II.  Domain-Organized, Loosely-Coupled Architecture
  III. Encapsulation & Strong Typing
  IV.  Documented, Agent- and Human-Friendly Public API
  V.   Simplicity & Readability
  VI.  Secret & Credential Safety
  VII. Backwards-Compatible Evolution

Added sections:
  - Technology & API Conventions
  - Development Workflow
  - Governance

Removed sections: none (initial version)

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check is a generic, constitution-driven
     placeholder; no change required (gates derived at plan time).
  ✅ .specify/templates/spec-template.md — aligns with Principle IV (testable requirements,
     measurable success criteria); no change required.
  ✅ .specify/templates/tasks-template.md — reconciled with Principle I: test tasks are now
     MANDATORY and test-first (write → confirm red → implement) rather than optional/on-request.

Follow-up TODOs: none.
-->

# flowbio Constitution

## Core Principles

### I. Test-First Development (NON-NEGOTIABLE)

Tests MUST be written before implementation code. The cycle is mandatory and strictly ordered:
write a failing test that defines the expected behavior, run it and confirm it fails (red),
write the minimum code to make it pass, run it and confirm it passes (green), then refactor
while keeping tests green. Implementation code MUST NOT be written before a failing test exists
for the behavior it provides.

**Rationale**: Test-first design forces clear specification of behavior, prevents untestable
designs, and guarantees that every behavior has a regression guard. For a client library other
teams depend on, an untested change is a breaking change waiting to happen.

### II. Domain-Organized, Loosely-Coupled Architecture

Code MUST be organized by domain (auth, samples, datasets, pipelines), not by technical role.
Each domain lives in its own module with its co-located models. Only genuinely cross-cutting
infrastructure (transport, exceptions, pagination) is shared. Modules MUST exhibit low coupling:
collaborators are received via dependency injection (e.g. resources are given a transport), not
constructed internally or reached through globals. Functions and classes MUST follow the single
responsibility principle and stay small.

**Rationale**: Domain organization keeps code discoverable and lets new domains slot in without
disturbing existing ones. Dependency injection and low coupling keep units independently testable
and make the layering (user code → resource → transport → httpx) enforceable.

### III. Encapsulation & Strong Typing

Implementation details MUST be hidden behind a minimal public surface. Internal modules, classes,
and methods are prefixed with `_` and MUST NOT be part of the documented API; only the layer that
owns a concern touches it (e.g. only the transport knows about `httpx`). Strong typing MUST be
used wherever practical: complete type hints on public signatures, frozen Pydantic models for
returned values, and `NewType` for primitive identifiers where it adds safety — but only when it
does not confuse end users.

**Rationale**: A small, well-typed public surface lets the internals evolve freely without
breaking callers, and gives both human developers and tooling precise contracts to rely on.

### IV. Documented, Agent- and Human-Friendly Public API

Every public interface (classes and public methods) MUST have a docstring, including a usage
example where applicable. The public API MUST be designed to be consumed by AI agents as well as
humans: predictable and consistent naming, explicit and typed signatures, structured return
values, and actionable error messages. Raw transport/HTTP errors MUST NOT leak to callers — all
failures surface through the typed `FlowApiError` hierarchy.

**Rationale**: This library is increasingly driven by automated agents as well as people.
Discoverable, self-describing, strongly-typed interfaces with predictable errors are usable by
both audiences without special-casing either.

### V. Simplicity & Readability

Simple, clean, maintainable solutions MUST be preferred over clever or complex ones. Names MUST be
self-documenting. Comments MUST be used sparingly and only to explain *why* a non-obvious approach
was taken — never as a substitute for clear code. Apply YAGNI: do not add abstraction, options, or
generality that no current requirement justifies.

**Rationale**: Readability and maintainability are the primary long-term costs of a library.
Cleverness that saves keystrokes today is paid back with interest in every future change.

### VI. Secret & Credential Safety

Credentials and tokens MUST NEVER be logged, persisted insecurely, or exposed in `repr`, error
messages, or exceptions. Refresh tokens MUST be handled via the HttpOnly cookie mechanism rather
than stored or surfaced by client code. Any new feature touching authentication MUST be reviewed
against this principle before merge.

**Rationale**: A client library holds users' live credentials. A single leak into a log line or
exception string can compromise every consumer; secret handling is a non-negotiable safety floor.

### VII. Backwards-Compatible Evolution

The library MUST follow semantic versioning. Backwards-incompatible changes to the public API
require a MAJOR bump and a documented migration path; during transitions (e.g. v1 → v2) the old
surface MUST remain available, with deprecation warnings, for a deprecation period before removal.
Commits MUST follow Conventional Commits, with the body explaining *why* and explicitly flagging
breaking changes; reference Linear or Sentry issues where applicable.

**Rationale**: Downstream code depends on this library's interface. Predictable, well-signposted
evolution is what makes it safe to upgrade, and clear commit history is what makes changes
auditable.

## Technology & API Conventions

- **HTTP**: `httpx` is the transport, supporting both sync and async from one codebase. The
  transport layer is the only code aware of `httpx`; resources and the `Client` never touch it
  directly.
- **Models**: Return values are frozen (`frozen=True`) Pydantic models; inputs are plain dicts.
- **Resource access**: Domain resources are exposed as read-only properties on `Client`
  (e.g. `client.samples`).
- **Status codes**: Use `HTTPStatus` constants over magic numbers in both code and tests.
- **Durations**: Time-based public parameters (e.g. in `ClientConfig`/transport) MUST be
  `timedelta`, not raw numeric seconds.
- **Exceptions**: Map HTTP status codes to the typed `FlowApiError` hierarchy in one place (the
  transport); never raise raw `httpx` errors to callers.

## Development Workflow

- **TDD gate**: The red-green-refactor cycle (Principle I) is followed for every behavior; verify
  the test fails before implementing.
- **Incremental delivery**: Stop between functionally complete steps so the change can be reviewed
  and committed; when stopping, state what the next step is.
- **Refactoring**: Proactively surface refactoring opportunities in code being touched, and propose
  the change before applying it.
- **Documentation**: Public interfaces ship with docstrings and examples as part of the same change
  that introduces them — not as a follow-up.
- **Commits**: Conventional Commits; header states what changed, body states why, breaking changes
  flagged explicitly.

## Governance

This constitution supersedes other development practices where they conflict. Amendments MUST be
proposed with a written rationale, take effect via a version bump, and be propagated to dependent
templates (`plan-template.md`, `spec-template.md`, `tasks-template.md`) and runtime guidance docs
in the same change.

Versioning policy (semantic):
- **MAJOR**: Backward-incompatible governance/principle removals or redefinitions.
- **MINOR**: A new principle or section is added, or existing guidance is materially expanded.
- **PATCH**: Clarifications, wording, and non-semantic refinements.

Compliance is verified at review time: every PR MUST be checked against these principles, and any
deviation MUST be justified in the PR (and recorded in the plan's Complexity Tracking when it
arises during planning). Unjustified complexity is grounds for rejection. For day-to-day runtime
development guidance, see `CLAUDE.md` and `docs/v2/architecture.md`.

**Version**: 1.0.0 | **Ratified**: 2026-06-05 | **Last Amended**: 2026-06-05
