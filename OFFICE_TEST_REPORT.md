# Office QA test report

Date: 13 November 2026 (Asia/Kolkata).
Branch: agent/verified-support-reads. Latest local code commit: c32f700.
No push, deployment, Appointy mutations, dependency, credential or environment
configuration changes. Pre-existing .bifrost.yaml remains untouched.

## Verdict

All six Appointy-facing public tools work against the tested QA fixtures using
only the supplied API key from the office host. All 24 get_entity modes have
successful real HTTP MCP reads. GCP retrieval remains blocked by the available
Google identity's log-view IAM permissions. Not all original product requirements
are fulfilled: explicit backend-access, missing-data and UI-verification gaps
are listed below. This is QA verification, not production/deployment verification.

## Execution

- 44 automated unittest tests: PASS (includes 21 frontend-helper parity cases).
- Actual local HTTP MCP server: health 200, initialize and tools/list succeed;
  seven tools and all 24 get_entity modes present.
- Main smoke: 35 successful Appointy calls, including continuation pages;
  four expected negative cases; an additional exact-center check.
- Expanded acceptance: 31 tool calls including five expected rejections;
  positive reads succeeded. Independently asserted group isolation, date bounds,
  complete appointment paging equality, and short/full settings equality.
- GCP tool called over MCP separately: structured failed result with
  `403 Permission denied for all log views`. Not a transport 503.
- Five direct API-key-only discovery probes rechecked outstanding backend access:
  all reached Appointy and returned GraphQL PermissionDenied (details below).

## Public tools

| Tool | Result | What was verified |
|---|---|---|
| mathnasium_get_group_context | PASS | Real group/company/location context read |
| mathnasium_find_center | PASS | Known center resolved; exact-center assertion passed |
| mathnasium_find_guardian | PASS | Scoped Rose lookup; Jacob returned one match, seven students, active=false, activeStatus=inactive, no warnings |
| mathnasium_find_student | PASS | Student#A-2 lookup; all returned IDs belong to configured group; guardian-scoped student read also succeeded |
| mathnasium_find_appointments | PASS | Student/customer/location/date filters, native cursors, default +/-31-day window, custom No-show filter, bounded-scan validation |
| mathnasium_get_entity | PASS for tested API reads | All 24 modes below; semantic/UI limits are not erased by successful responses |
| mathnasium_search_custom_logs | BLOCKED for retrieval | Unfiltered query rejected correctly; actual read fails Google log-view IAM check |

Jacob's fresh API-key-only result matches the QA Inactive badge inspected on
12 November. Guardian status no longer uses a hard-coded true or activeMembership.
Failed/incomplete enrollment evidence is null/unknown. Exact guardian creation/
update timestamp and primary-profile timezone UI comparisons remain incomplete.

## All get_entity modes

| Mode | API/MCP result | Meaning / limitation |
|---|---|---|
| appointments | PASS | Common entity path uses bounded appointment reader |
| services | PASS, page 2 | Session-type records; no exhaustive UI audit of all records |
| employees | PASS, page 2 | Staff, scope and roles returned; no exhaustive permissions/schedule UI audit |
| resources | PASS | Scoped resource read |
| group_settings | PASS | Group settings read |
| company_settings | PASS | Short/full company ID results deep-equal |
| location_settings | PASS | Short company/location scope and active fixture settings read |
| apps | PASS | Scoped apps read |
| booking_rules | PASS | Location rule and service override read; previously inspected UI values match |
| portal_settings | PASS | Portal/recurring settings readable; previously inspected toggles match; AutoInvites UI value not fully verified |
| availability_rules | PASS, page 2 | Stored rules, recurrence, capacities, services and dates |
| availability_window | PASS, page 2 | Bounded window read and local continuation; not an API-native cursor |
| bookable_slots | PASS, page 2 | Validator/slot response works. Sample rows were BookedAppointment, not demonstrated free slots. errorMessage fields were empty, not actual reported errors |
| bookable_durations | PASS, empty fixture | API returns an empty duration list; nonempty duration/UI parity not established |
| enrollment_balance | PASS | Enrollment remaining-bookable monthly buckets; not monthly booked/attended totals or sync-history balance |
| recurring_series | PASS | Series and rule via seed appointment; not direct recurring-ID access |
| attendance_statuses | PASS | Custom status definitions returned |
| activity_logs | PASS | Empty filtered smoke window; expanded historical read returned events. No controlled edit performed |
| guardian_profile | PASS | Creation/update timestamps and profile timezone returned |
| student_audit | PASS | Audit timestamps and actor IDs returned |
| record_metadata | PASS | Company/location metadata decoded separately; no invented inheritance. Location timestamps are epoch placeholders in tested fixture |
| instructor_services | PASS, page 2 | Instructor/session-type assignment read |
| consumer_appointment_count | PASS | Undated count, not enrollment monthly usage |
| radius_student | PASS | Current Radius projection, not last-sync request/result/history |

Availability UI evidence from 12 November's fresh Chrome queries: 48 stored rules,
nine bounded-week rule groups; Alyssa's 28 blocks agree on times/capacities after
Asia/Kolkata conversion. Opened Sunday block agrees on 09:00-13:00, capacity 1,
weekly Sunday and five named session types. Stored and bounded versions have the
same block IDs/common fields, but array order differs. This was a sampled UI
comparison; the office retry verified actual API-key-only MCP access anew.

## Acceptance assertions

- Student group isolation: PASS using approved Student#A-2 substitute. Exact
  MT-1711 name is unknown, so exact ticket reproduction is not claimed.
- Location-only appointments: rejected as intended.
- 63-day appointment window: rejected as intended.
- Student with no dates: default window exactly 62 days, centered on call time.
- Page size 1 exhausted vs page size 50: same two ordered appointment IDs;
  no duplicates or gaps for this fixture.
- No-show: matching consumer custom status confirmed. Overall appointment remains
  APPOINTMENT_CONFIRMED; consumer attendance and overall status are distinct.
- Location/service booking-rule reads: success; previously compared UI samples.
- Availability 32 days, slots 8 days, activity 91 days: all rejected as intended.
- Full/short company settings: deep-equal.
- Existing negative cases: missing slot inputs, foreign-group settings and
  unfiltered GCP scans rejected.

## Existing APIs still denied to the API key

Retested from office, same QA API key. Responses are HTTP JSON GraphQL
`Not permitted`, extensions.code=PermissionDenied, not Cloudflare HTML:

| Existing API | Needed for | Backend/access request |
|---|---|---|
| enrollmentUnderUtilizationReport | Monthly allowance vs booked counts | Authorize read-only support service access |
| mathnasiumOverBookingReport | Future overbooking | Authorize read-only support service access |
| notificationReport | Invite/welcome/reset send history | Authorize read-only support service access; this alone does not supply delivery/suppression data |
| appointmentsOfOrder(recurringId) | Direct recurring-ID lookup | Clarify supported scope/service authorization; seed-appointment workaround already works |

The report APIs worked in the earlier authenticated-browser discovery. Direct
recurring-ID access was denied in both earlier auth modes. No wrappers for these
blocked reads were added. Removing Cloudflare blocking does not fix these grants.

## Backend data work still needed

These are prior API-discovery gaps, not newly disproved by successful smoke tests:

1. Sync provenance and balance journal: last Radius value, received/committed
   time, request ID/result and last five changes.
2. Email delivery/suppression: provider delivery/bounce/failure reasons and
   suppression status/history, beyond notification send events.
3. Audit completeness: service/enrollment audit fields and valid location audit
   timestamps; investigate null/epoch placeholders.
4. Complete deleted-availability history: stable target ID and before-state for
   times, capacity, recurrence and staff/service links. Existing audit events
   are not complete recoverable snapshots.
5. Exact per-enrollment attendance/cancellation totals where enrollments overlap:
   authoritative consumed-enrollment linkage or status breakdown.
6. Structured all-reasons eligibility if required as one authoritative answer.
   Existing eligible IDs/slots can return no reason; composition is narrower.
7. Timezone-rule version/rendering provenance, if that requirement is retained.
8. Original students(parent=group) cross-group bug: backend investigation still
   relevant, though MCP now uses a verified group-scoped alternative and checks IDs.

No new backend availability read API is needed for current rules/window reads.
Full deleted-block history is a separate backend requirement. Complete monthly
usage needs report access and, for exact status attribution, the linkage above.
Booking URLs/profile timezones/settings are accessible, but exhaustive verification
for every inactive/virtual center or every setting is not claimed.

## Remaining non-backend verification/access work

- Use an authorized GCP identity for live logs; then verify real multi-page logs,
  broad-window latency and >=3 concurrent reads. Unit tests are not live proof.
- API-key-only access is now working on the office network. Exact earlier
  Cloudflare challenge rule is unknown; do not assume all deployment networks pass.
- Complete enrollment-balance UI comparison: earlier QA route crashed blank.
- Locate/confirm AutoInvites UI source and exact primary guardian audit/profile UI
  fields; metadata read success alone does not settle effective-setting semantics.
- Controlled activity edit/actor-name UI test was not performed (no writes).
- Nonempty duration/free-slot fixtures and exhaustive eligibility validation remain.
- No production ticket acceptance, deployment verification or load test claimed.

## Evidence

Private raw captures remain outside version control:

- /private/tmp/math-office-unit-tests.txt
- /private/tmp/math-office-full-smoke.txt
- /private/tmp/math-live-results.json
- /private/tmp/math-office-acceptance/ (31 call captures, schema and assertions)
- /private/tmp/math-office-backend-access.json
- /Users/appointy/Downloads/qa-chrome-read-evidence.json

Backend classification originates in analysis_outputs/appointy-api-discovery-2026-11-11
(read-probes.json, capability-matrix.json, backend-requests.json). No credentials,
private raw responses or service-account JSON are included in this report.
