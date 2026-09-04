# SCADA Repository Agent Rules

This file is the operational source of truth for agent-driven development in this repository.

## Rule Levels

- MUST: mandatory requirement
- SHOULD: recommended practice
- MAY: optional guidance

## 1) Language and Deliverables

### MUST
- Terminal interaction with the project owner is in Spanish.
- Code artifacts are in English: identifiers, variable names, function names, class names, inline code comments, and commit messages.
- Project documentation is written in English and stored in `documents/`.
- Project planning artifacts are written in Spanish and stored in `Plan/`.

### SHOULD
- Use naming conventions:
  - `documents/YYYY-MM-DD-topic.md`
  - `Plan/YYYY-MM-DD-plan-<tema>.md`

## 2) Architecture and Service Boundaries

### MUST
- Build the system as independent services with clear responsibilities.
- Keep each service independently deployable.
- Define explicit versioned contracts per service (REST, gRPC, or events).
- Provide a `Dockerfile` for every runnable service.
- Use `docker compose` as the standard local orchestrator.

### SHOULD
- Keep service boundaries aligned with business capabilities.
- Prefer small, focused services over multi-purpose services.

## 3) Docker Networking and Service Communication

### MUST
- Use Docker networks for inter-service communication.
- Use service DNS names across containers; do not use `localhost` for inter-container calls.
- Define at least an internal network (for example `backend`).

### SHOULD
- Separate edge traffic from internal traffic (for example `edge` + `backend`).
- Publish host ports only for edge services (gateway/reverse proxy) when possible.

## 4) Local Operations via Shell Scripts

### MUST
- Expose core local operations via `.sh` scripts in `scripts/`.
- Maintain at least:
  - `scripts/up.sh`
  - `scripts/down.sh`
  - `scripts/restart.sh`
  - `scripts/logs.sh`
  - `scripts/status.sh`

### SHOULD
- Use `set -euo pipefail` in scripts.
- Print clear execution messages and return meaningful exit codes.
- Support useful parameters where relevant (`service`, `--build`, `--detach`).

## 5) Configuration and Secrets

### MUST
- Use environment variables for runtime configuration.
- Document required and optional variables per service.
- Keep real secrets out of git.
- Version `.env.example`; keep real `.env` files ignored.
- Never hardcode credentials, tokens, or secret endpoints.

### SHOULD
- Use domain prefixes (`AUTH_`, `DB_`, `MQ_`, etc.).
- Validate critical variables at startup and fail fast with explicit errors.

## 6) Quality, Testing, and Definition of Done

### MUST
- Provide minimum unit tests per service.
- Provide integration tests for primary service contracts.
- Run relevant tests before considering a task complete.
- Update contract tests when APIs/events change.

### SHOULD
- Automate linting and formatting per service.
- Define coverage thresholds per service and improve them over time.

### Definition of Done (MUST)
- English code artifacts and code comments.
- Config and secret policy compliance.
- Dockerized service works through shell-script workflow.
- Relevant tests pass.
- Required docs/plans are updated in correct folders.

## 7) Git and Pull Request Workflow

### MUST
- Use short-lived branches (`feature/*`, `fix/*`, `chore/*`).
- Do not push directly to `main`.
- Keep commits atomic and in English.
- Use pull requests for all changes.

### PR checklist MUST include
- Scope and goal
- Impacted services
- Test evidence
- Documentation and planning updates
- Contract impact statement

## 8) CI/CD Baseline

### SHOULD
- Use per-service stages: build, lint, tests, basic security scan.
- Block merge when required quality gates fail.

## 9) Security Baseline

### MUST
- No secrets in repository.
- Use trusted base images.
- Run containers as non-root where feasible.

### SHOULD
- Scan dependencies and images for vulnerabilities.
- Follow a regular patch/update cadence.

## 10) Observability Baseline

### SHOULD
- Use structured logs per service.
- Include correlation identifiers (`trace_id`/`request_id`) when possible.
- Track minimum health and latency metrics.

## 11) Backup and Recovery

### SHOULD
- Maintain backup/restore policy documentation for critical data in `documents/`.
- Periodically test restore procedures.

## 12) Task and PR Verification Checklist

Before closing a task or merging a PR, verify:

- Language rules were followed (Spanish interaction, English code artifacts).
- Documentation (English) is in `documents/` when needed.
- Planning (Spanish) is in `Plan/` when needed.
- Services remain dockerized and compose/network rules are respected.
- Local shell scripts are usable for operations.
- Relevant tests were executed and passed.
- Security/secrets rules are respected.
- Contract updates are included when interfaces changed.
