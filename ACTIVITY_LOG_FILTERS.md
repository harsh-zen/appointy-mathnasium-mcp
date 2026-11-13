# Activity-log filtering fix

## Changes

- Added upstream displayEventName, userEmail, userId and ipAddress filters to
  mathnasium_get_entity for activity_logs only.
- Event and actor filters are forwarded server-side before upstream pagination.
- Echo applied fields in filters and bind each to continuation cursors.
- Reject unsupported activity target/booking filters with actionable errors.
- Explicitly reject legacy type instead of the SDK silently dropping it.
- Reject actor/event-name arguments on other entity types; reject blank values.
- No API credentials, deployment config, raw data captures or backend changes.

## Verification

API-key-only QA discovery: historical baseline 115 events. Confirmed event-name
filter returns four; known actor-ID filter returns 101. Nonexistent event name,
actor email, actor user ID and IP each return zero without GraphQL errors.
This verifies accepted upstream filtering, not full matching semantics for every
possible input. No email/IP positive fixture was independently confirmed.

Regression tests cover forwarding/echo, all unsupported fields, blank values,
filter-bound cursors, schema descriptions and legacy type rejection. Real HTTP MCP
checks and full smoke results are recorded after completion below.

## Backend-ticket comment

Request: extend the existing activityLogs filter with indexed target-entity
filtering. The current ListActivityLogFilterInput supports dateRange,
activityLogEventId, displayEventName, userEmail, userId and ipAddress, but no
service/affected-entity filter. MCP now rejects unsupported filters instead of
silently ignoring them; it cannot avoid scanning pages to find a service change.

Please provide:

1. A documented targetEntityId(s)/targetEntityType filter, including explicit
   serviceId/settings-scope filtering for location rules vs service overrides.
   Match full canonical IDs; document whether short IDs are accepted. Keep actor
   userId distinct from the affected entity. Preserve tenant/group authorization.
2. Apply target/date/event/actor filters together on the server BEFORE pagination
   and counting, with suitable indexes. Do not simply filter each fetched page.
3. Stable target IDs in events, actor ID, timestamp, setting scope and changed
   field paths. Return before/after values if retained, and an explicit indication
   when they were not recorded. Never infer a missing before-state.
4. Deterministic timestamp + tie-breaker order and reliable continuation. State
   historical retention/backfill limits for events lacking target identifiers.

Acceptance: a location's Sep-Nov history can be queried for a single session
service's cancellation/reschedule-rule changes without scanning unrelated pages;
all returned events match the target, pages neither skip nor duplicate events,
actor and target filters stay distinct, and unknown old/new values remain unknown.
No write endpoint is requested. This is a backend extension, not an MCP local
post-filter workaround. A measured latency target should be agreed with backend.

Completed verification: 50 unit tests pass; all 35 full QA Appointy HTTP smoke
calls pass. Additional HTTP tests pass for event-name/actor positive matches,
four nonexistent-filter controls, a distinct second page, changed-filter cursor
rejection, and explicit entityId/serviceId/type/studentId rejections. Existing
local GCP check remains IAM-denied, unrelated to this change. Compile and diff
whitespace checks pass. Private evidence is in /private/tmp/math-activity-*;
no raw audit events or credentials are committed.
