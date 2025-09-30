# Test Plan

## Overview
This plan enumerates each Python module in `src/twitch_subs` (except `__init__.py`) and outlines the
behaviour that must be exercised to reach >=95% line/branch coverage while focusing on real logic and
async flows. Existing tests already cover some surface area; this plan highlights the remaining work
and additional scenarios required for deterministic, high-signal tests.

## Domain Layer

### `domain/models.py`
- Validate `BroadcasterType.is_subscribable` for all enum values.
- Ensure `State` behaves like a mutable mapping (getitem, setitem, delitem, iteration, copy).
- Exercise `SubState` default timestamp generation deterministically.
- Property-based checks for `UserRecord`/`LoginStatus` immutability and equality semantics.

### `domain/exceptions.py`
- Verify custom `message()` implementations and inheritance chain.

### `domain/ports.py`
- Runtime smoke checks that concrete fakes implementing each protocol satisfy `isinstance` checks.
- Ensure docstring-only protocol methods are excluded from coverage or exercised via dummy
  implementations.

## Application Layer

### `application/logins.py`
- Simple subclass that returns watchlist data; confirm idempotent behaviour.

### `application/watchlist_service.py`
- CRUD semantics against in-memory repo plus branch where `add` short-circuits on existing login.

### `application/watcher.py`
- `check_login` happy-path and missing-user path.
- `run_once` transitions:
  - Subscribable -> notify change + persist `SubState` with `since` timestamp.
  - No change path keeps `since` when already subscribed.
  - Stop event triggers early exit with `False`.
- `_report` builds report dict from repo contents.
- `watch` loop:
  - Successful iteration increments counters and schedules report dispatch.
  - Error path increments `errors` when `run_once` raises.
  - Stop-event breaks loop and triggers notifier shutdown.
  - Interval waiting respects already-set stop event (no delay).

## Infrastructure Layer

### `infrastructure/repository_sqlite.py`
- Already largely covered; extend to include `list_all` and `set_many` no-op early return branch.

### `infrastructure/logins_provider.py`
- Ensure it returns sorted copy of repository data.

### `infrastructure/telegram.py`
- `TelegramNotifier` formatting for start/stop/change/report messages using a stub bot capturing
  payloads. Cover error handling when `send_message` raises.
- `IDFilter` behaviour (already partially covered) plus branch for accepted ID.
- `TelegramWatchlistBot` pure helpers (`_handle_add/remove/list`, `handle_command`).
- Command handlers using fake `Message` objects to verify reply text batching and parse mode options.
- `run`/`stop` orchestrate dispatcher lifecycle using an in-memory stub dispatcher.

### `infrastructure/twitch.py`
- HTTP client interactions already well covered; ensure rate limiter and token refresh branches stay
  deterministic via mocked transport/time control.

### `infrastructure/error.py`
- Message formatting already covered; add tests for dataclass string interpolation.

## CLI Layer

### `cli.py`
- `validate_usernames` rejects invalid names and passes valid ones.
- `_get_notifier` returns `None` when credentials missing and real notifier when present (covered but
  revalidated after refactor).
- `run_watch` integrates `Watcher.watch` with `WatchListLoginProvider` and stop event.
- `run_bot` ensures bot `run` is awaited and `stop` cancels gracefully.
- `state` subcommands hitting repo (with temporary DB) covering success/failure exit codes.
- `watch` command: signal handler registration, watcher & bot tasks created, stop triggered.
  (Use in-memory loop via `asyncio.new_event_loop()` and monkeypatch to prevent real signals.)
- `add`, `list`, `remove` commands using real SQLite repo and notifier stub to exercise notification
  batching, quiet flag, and error exit codes.

### `main.py`
- Ensure CLI entrypoint returns `SystemExit` with CLI main result (trivial import coverage already
  satisfied).

## Container & Config

### `config.py`
- Already covered, maintain tests ensuring environment parsing for `database_echo`.

### `container.py`
- Instantiate container with in-memory SQLite URL and verify lazy singletons for repositories,
  notifier, watcher, and bot reuse same instances (ensuring branches executed).

## Tooling & Documentation

- Enforce `--cov-fail-under=95` inside `pyproject.toml`.
- README: add instructions for running tests with coverage via `uv`.

## Testing Approach

- Use `pytest` with `pytest-asyncio` for async flows.
- Prefer real SQLite databases via temporary files or `:memory:` engines.
- Replace heavy dependencies (aiogram bot/dispatcher) with lightweight fakes mimicking behaviour.
- Use `freezegun`-style manual patching or helper fixtures to control timestamps.
- Ensure tests remain deterministic by stubbing `time.time` and `datetime.now` where necessary.

