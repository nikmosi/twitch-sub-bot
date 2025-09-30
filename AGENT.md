## Mission

An autonomous Python engineer. Your goal: design, build, and test code following **DDD**, **Hexagonal Architecture**, **Dependency Injection**, and **SOLID** principles. Use proven libraries, keep builds reproducible with **uv**, maintain **≥95% test coverage**, ensure strong typing, and write deterministic, maintainable code.

---

## Architectural Principles

* **DDD + Hexagonal (Ports & Adapters):** domain logic must be independent of infrastructure.
* **SOLID:** small, focused abstractions; depend on interfaces, not implementations.
* **Clean Architecture:** dependencies point inward; stable boundaries.
* **Idempotency and determinism:** core logic should be predictable and side-effect free.
* **Asynchronous by default:** never convert async code to sync for convenience; test async code as async.

---

## Layers and Boundaries

* **Domain:** entities, value objects, domain services, policies, events, exceptions. No imports from infrastructure.
* **Application:** use cases, orchestration, transactions, input validation. Depends only on domain ports.
* **Ports:** protocols/interfaces (`Protocol`) implemented by adapters.
* **Adapters (Infrastructure):** database, HTTP, brokers, filesystem, time, UUID, logging.
* **Interface:** CLI/HTTP/RPC endpoints. Thin controllers only.
* **Composition Root:** DI container that wires everything together.

---

## Core Stack

* **Environment & builds:** `uv` (optionally Nix flakes).
* **Testing:** `pytest`, `pytest-asyncio`, `pytest-cov`, `hypothesis`, `pytest-timeout`.
* **HTTP:** `httpx` (async); HTTP mocking: `respx`.
* **Database:** `SQLAlchemy` 2.x; use in-memory SQLite or `testcontainers` for integration tests.
* **DI:** `dependency-injector` or simple factory-based DI with `Protocol`.
* **Configuration:** `pydantic` v2 (`BaseSettings`) for env/secret validation.
* **Serialization:** built-in `pydantic` or `msgspec` (for performance-critical cases).
* **Logging:** stdlib `logging` + structured logging (`structlog` or JSON formatter).
* **Typing & style:** `mypy`, `ruff` (lint + fmt), optionally `pyright`.
* **CLI:** `typer` or `click`.
* **Time & UUID:** abstractions (`Clock`, `IdProvider`) for deterministic testing.
* **Test data factories:** `factory_boy` or `pydantic-factories`.
* **Time freezing:** `freezegun`.

---

## Testing Policy

* **Goal:** ≥95% line and branch coverage across `src/` (excluding `__init__.py` and generated files).
* **Priority:** integration and logic-level tests, minimal mocking. Use real components, in-memory DBs, or local fakes.
* **Async:** write `async def` tests with `pytest-asyncio`; do not refactor async code to sync.
* **Determinism:** fix random seeds, freeze time, and stub UUIDs at boundaries.
* **Test levels:**

  * **Unit (Domain):** invariants, boundaries, exceptions.
  * **Application:** scenarios, transactions, idempotency, retries.
  * **Integration:** repositories, HTTP clients, migrations, schemas.
  * **E2E/CLI/API:** black-box tests, happy-path, edge cases, error handling.
* **Performance:** unit tests <2s total, integration tests <10s.
* **Regression:** add a test for every bug fix.

---

## Observability and Diagnostics

* Structured logging with proper levels (DEBUG, INFO, WARN, ERROR).
* Key metrics at port boundaries: attempts, successes, failures, latency.
* Optional tracing: OpenTelemetry.

---

## Configuration and Secrets

* Use `pydantic` Settings with priority: `env > .env > defaults`.
* No secrets in VCS. Use stubs or fixtures in tests.
* Separate profiles: **dev / test / prod**.

---

## Agent Workflow

1. **Initialize project**

   * Generate `pyproject.toml` for `uv` and core stack.
   * Scaffold layers: `domain/`, `application/`, `adapters/`, `interfaces/`, `di/`.
   * Enable `ruff`, `mypy`, and `pre-commit` hooks.

2. **Test planning**

   * Create `TEST_PLAN.md` listing modules, test levels, boundaries, and risks.

3. **Build DI and ports**

   * Define `Protocol` interfaces.
   * Extract side effects behind ports.
   * Build the composition root and dependency graph.

4. **Implement functionality**

   * Domain rules in domain services.
   * Infrastructure in adapters.
   * External dependencies via DI.

5. **Write tests**

   * Develop tests alongside code.
   * Use `sqlite://:memory:` for repository integration tests.
   * For HTTP, use `respx` or local fakes — never real network calls.

6. **Quality control**

   * `ruff` and `mypy` must pass.
   * Coverage ≥95%.
   * Eliminate flaky tests immediately.

7. **CI**

   * Jobs: lint, type-check, test + coverage, build.
   * Enforce `--cov-fail-under=95`.

---

## Recommended Commands (Makefile or justfile)

```bash
uv venv
uv sync

# Linting & typing
uv run ruff check .
uv run ruff format .
uv run mypy src

# Tests & coverage
uv run -m pytest -q --maxfail=1
uv run -m pytest --cov=src --cov-report=term-missing --cov-branch --cov-fail-under=95

# E2E / CLI example
uv run python -m app.cli --help
```

---

## Commit and PR Guidelines

* Small, atomic PRs.
* Code changes must include tests and documentation.
* Explain architectural decisions in PR descriptions.
* No flaky tests or network-dependent tests allowed.

---

## Definition of Done

* All lint, type checks, and tests pass.
* **≥95% test coverage**, no critical file below 90%.
* Async paths are covered by async tests.
* Domain layer does not depend on infrastructure.
* `README` includes testing instructions.
* `TEST_PLAN.md` is up-to-date.
