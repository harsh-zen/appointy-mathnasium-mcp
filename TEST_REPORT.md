# Verified support reads: implementation and verification

Date: 12 November 2026. Branch: `agent/verified-support-reads`.
No push, deployment, auth configuration or backend changes.
The pre-existing untracked `.bifrost.yaml` is intentionally excluded.

## Implemented

- Extend `mathnasium_get_entity` with 16 explicit, read-only entity types documented
  in README: booking/portal settings, current availability rules and date windows,
  computed bookable slots/durations, remaining-bookable buckets, seed-based recurring
  series, attendance definitions, audit evidence, profile/audit reads, metadata,
  instructor assignments, undated counts and current Radius student projection.
- Replace local appointment-calendar filtering/offset paging with verified upstream
  student, booking-customer, date, overall-status and custom-attendance filters,
  start-time ordering, native cursor paging and creator/status/history evidence.
  Direct recurring-ID reads remain excluded; a seed appointment can read its series.
- Route the existing common appointment entity read through the bounded filtered
  appointment implementation. Location-only unbounded calls are rejected.
- Paginate employees/services upstream. Include scoped staff roles, module names,
  locations, profile timezone and audit fields.
- Accept short/full settings scope IDs; use direct company/location reads if a
  valid entity is absent from cached context. Decode metadata without merging
  company and location values or inventing inheritance.
- Replace the defective group-parent student list with verified group-scoped search,
  validate candidate IDs before hydration and reuse hydrated details. Keep scoped
  guardian lookup and enrollment-based scheduling status behavior.
- Add available guardian/student audit fields. Missing timestamps remain unknown;
  service/enrollment timestamp gaps are not fabricated.
- GCP: read a native page with an explicit RPC timeout and no SDK retries. Return
  at most 50 rows, filter-bound continuation and truthful partial coverage under
  a maximum 25-second application budget. Summary mode is page-level only.
- Add read-only MCP annotations, usage guidance and a QA-only HTTP smoke harness.

## Automated checks

35 unittest tests pass, including:

- Existing enrollment/date, booking URL, guardian scope and session-link regressions.
- Native appointment filters, distinct cursor pages, cursor/filter binding, stable
  default windows, overall vs custom attendance and unsupported recurring-ID errors.
- Group validation, short/full IDs, cache-miss settings fallback and scope conflicts.
- Availability window/argument validation, output bounds, native/local continuation,
  policy preservation and malformed/missing continuation errors.
- Student search never hydrates a foreign-group candidate.
- Log native page token/timeout propagation, JSON payload conversion, retry behavior,
  timeout-to-partial behavior, summary semantics and three concurrent calls.
- MCP catalog contains seven tools; modified read tools have read-only annotations.

Also pass: Python compilation and `git diff --check`.

Run using the repository's pinned dependencies (tested in an isolated environment):

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
python -m py_compile src/appointy_mathnasium_mcp/*.py tests/*.py scripts/live_qa_smoke.py
```

The global machine runtime was also checked, but it had MCP 1.13.1. The final
verification uses MCP **1.28.1**, httpx **0.28.1**, and google-cloud-logging **3.17.0**,
which satisfy the repository constraints. No dependency files were changed.

## Live Appointy QA checks

All Appointy checks use only `x-api-key`, with configured group/support-user
context, against `https://qa-mathnasium-admin.appointy.com`; no browser cookies.
No production Appointy reads or mutations were used.

The HTTP smoke starts the actual server, checks `/health`, initializes an MCP
client, lists all seven tools and calls them over `/mcp`:

- 35 successful Appointy tool calls covering all 16 additions, existing lookup tools,
  employees/services, settings/apps/resources, and continuation pages.
- Appointment, employee and service second pages contain different IDs.
- Confirmed guardian, student and center matches (not merely HTTP 200).
- Negative cases reject location-only appointment scans, missing slot arguments,
  foreign-group settings IDs and unfiltered log scans.
- Additional direct QA checks pass for three cache-miss settings fallbacks,
  company-only metadata, full-ID-only profile/series/balance reads, ascending
  appointments, cancelled status and custom-attendance filters. Empty filtered
  results are reported as empty, not evidence that an arbitrary ticket is solved.

Reproduce with QA environment variables already set:

```sh
PYTHONPATH=src python scripts/live_qa_smoke.py
```

The harness refuses a non-QA base URL and stops the server when finished.
Captured responses and server logs are written only to `/private/tmp`, not git:
`math-live-results.json` and `math-http-server.log`.

## GCP live verification limitation

The available local application-default identity receives:
`403 Permission denied for all log views` for the configured production logs.
This is returned as a structured tool error, not an HTTP transport failure.
The newer service-account file previously supplied is no longer at its supplied path.
Consequently **successful live GCP retrieval, real >50-row continuation and broad
production-query latency are not verified in this change**. Automated tests cover
these control paths; they do not substitute for an authorized live GCP test.
No credential, IAM grant, secret or deployment setting was changed to bypass this.
Application deadlines cannot guarantee that a proxy/infrastructure never emits 503.

## Explicit exclusions

No blocked utilization/overbooking/notification reports, direct recurring-ID API,
provider delivery/suppression history, sync/balance journal, complete deleted-block
snapshots, missing service/enrollment audit storage, timezone-rule provenance or
all-reasons eligibility endpoint. Current Radius balance is not sync history;
remaining-bookable buckets are not booked/attended counts; slots/capacity are not an
exhaustive diagnosis or independently verified free-seat calculation. Group-context
response-size optimization remains outside this change.
