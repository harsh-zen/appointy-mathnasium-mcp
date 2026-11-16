# Three report-read verification

Date: 16 November 2026. Local branch: agent/report-read-tools. Not pushed/deployed.
New get_entity modes: monthly_utilization, overbooking_report,
notification_history. Seven top-level tools remain; entity enum now has 27 modes.

## Implementation

report_reads.py owns report validation, upstream requests and pagination.
support_reads.py delegates the explicit report types. support_queries.py contains
allowlisted reads. tools.py exposes reportMonth and notificationAddress and updates
argument descriptions. No credential, environment config or backend changes.

- Company/location parentId required; consistent scope/group checks.
- reportMonth YYYY-MM for utilization and overbooking. Utilization forwards the
  timezone and start-month anchor; subsequent month buckets can be returned.
- Notification window <=24 hours, EMAIL channel, optional recipient address.
- Page size <=50. Native offset continuation for utilization and notifications;
  local continuation for overbooking (upstream exposes no paging arguments).
- All report arguments and page size are bound into cursors.
- Reject unsupported student/guardian/enrollment/service/entity/activity filters.
- Source-truncated overbooking results return status=partial and a warning;
  local page exhaustion does not claim to recover omitted upstream rows.
- Keep raw counters and send-event meaning. No fabricated attendance, delivery,
  suppression or historical Radius balance fields.

## Real production tests

Used the existing production key from the user's local env file, loaded only into
the test process. No cookies. Started the patched local HTTP MCP on 127.0.0.1:8143
and called it using the real MCP client. Production Appointy fixture: Teddington.
No production records were written or changed. Temporary server stopped afterward.

| Check | Result |
| --- | --- |
| Health/schema | PASS: seven tools, 27 entity modes |
| Monthly utilization | PASS: nonempty page; first enrollment has three booked-month buckets |
| Utilization next page | PASS: distinct row, native continuation |
| Overbooking November | PASS: total=0, empty rows, downloadLimit=1000; no claim that a positive overbooking fixture was tested |
| Notification one-day window | PASS: total=224 send events, downloadLimit=1000 |
| Notification next page | PASS: distinct event |
| Recipient positive filter | PASS: all returned addresses match supplied address |
| Recipient negative control | PASS: zero rows, not an error |
| Changed-limit cursor | PASS: utilization/notification continuation rejected |
| Two-day notification window | PASS: rejected before request |
| Unsupported student filter | PASS: explicitly rejected |
| Invalid month | PASS: explicitly rejected |

These tests establish the new MCP-to-production-API path, not deployment of this
local code. No production booking/admin UI comparison or exact #12735 fixture
reproduction was performed. Month/timezone semantics outside the tested Europe/
London and UTC anchors are not independently verified against the UI. Overbooking
nonempty pagination/truncation paths are covered with unit fixtures, not a positive
production overbooking case. No load test or timeout guarantee is claimed.

## Automated verification

59 unit tests pass (50 existing plus nine report test methods). Includes counter
preservation, native/local paging, truncation disclosure, cursor/filter binding,
month/timezone/date/scope/argument validation, malformed pagination, error
propagation, and schema exposure. Compile and diff-whitespace checks pass.

Existing full QA HTTP smoke: results recorded after the run completes below.
These tests use the existing QA fixtures and do not assume QA report grants exist.

## Agent guidance

Use REPORT_AGENT_INSTRUCTIONS.md as the prompt update. Remove obsolete blanket
report-access limitations; keep delivery/suppression, sync history and exact
attendance-attribution gaps. The recurring seed-appointment flow is unchanged.

## Private evidence (not in git)

- /private/tmp/math-new-reports-live-results.json
- /private/tmp/math-new-reports-live-output.txt
- /private/tmp/math-new-reports-server.log
- /private/tmp/math-report-unit.txt
- /private/tmp/math-reports-existing-smoke.txt

Completed existing-tool regression: all 35 QA Appointy HTTP smoke calls and
expected negative cases pass. Local GCP smoke remains IAM-denied, unchanged and
unrelated to these report reads. The previously tested deployed GCP identity is
separate; this run made no deployment or GCP credential changes.
