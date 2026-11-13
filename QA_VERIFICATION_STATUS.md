# QA verification status - 12 November 2026

No push or deployment. Guardian fix is local commit `c32f700` on
`agent/verified-support-reads`. No authentication or infrastructure changes.

## Current blocker: QA Cloudflare challenge

Two independent API-key-only clients (httpx and curl) receive HTTP 403 from
`https://qa-mathnasium-admin.appointy.com/graphql` before Appointy executes the
initial AppQuery. The response is HTML titled `Just a moment...`, not an Appointy
JSON authorization error. curl response headers include:

```text
HTTP/2 403
content-type: text/html; charset=UTF-8
cf-mitigated: challenge
server: cloudflare
cf-ray: a5975a334b23a92c-MAA
```

This cannot be fixed by changing guardian enrollment logic or retrying API keys.
The infrastructure owner must inspect that Ray ID and approve a narrowly scoped
machine-access policy or provide an approved API ingress for the QA MCP caller.
Do not broadly disable protection, copy browser session credentials, or treat a
browser-authenticated request as proof of API-key-only MCP access.

After approved access is restored, rerun the local HTTP MCP guardian test against
Jacob's visible Inactive badge, then the complete QA smoke and UI acceptance suite.
The patched guardian live test is **not passed** yet.

## Public tools

Earlier evidence below comes from saved real local HTTP MCP responses captured
on 12 November, before the challenge started. It is not a fresh successful rerun.

| Tool | Earlier API/MCP evidence | UI verification / remaining gap |
|---|---|---|
| mathnasium_get_group_context | Successful group/company/location read | Math Test company fields compared; complete tree not exhaustively UI-audited |
| mathnasium_find_center | One matching center returned | Selected company fields compared; no exhaustive URL audit |
| mathnasium_find_guardian | Earlier scoped read returned one match | Jacob UI Inactive reconfirmed. New status code passes regression, but patched live call is blocked by Cloudflare |
| mathnasium_find_student | Group-scoped Student#A-2 returned two candidates | Approved substitute regression only; exact MT-1711 name unavailable |
| mathnasium_find_appointments | Filtered read and two native cursor pages succeeded | Two history entries and No-show fixture compared with UI; pagination equal/no duplicates; default window and validation pass |
| mathnasium_get_entity | All 16 added entity types had successful earlier API responses | Detailed coverage below; successful response is not exhaustive UI parity |
| mathnasium_search_custom_logs | Validation/timeout/pagination covered by automated tests | Successful GCP read blocked by available identity's log-view permissions; unrelated to QA Cloudflare |

## get_entity additions

| Entity type | Earlier real response | Remaining limitation |
|---|---|---|
| booking_rules | Location and service override succeeded | Inspected notice/horizon/cancellation/reschedule values match UI |
| portal_settings | Successful | Inspected portal/recurring toggles match UI; AutoInvites UI value not verified |
| availability_rules | Nonempty rules, capacity, service links, recurrence and dates; second page succeeded | Not exhaustive UI comparison; no promised complete deleted-block history |
| availability_window | Two rule items plus continuation succeeded | Date-bounded API read works; exact UI calendar parity not verified |
| bookable_slots | Two slot items plus one slotErrors entry | Must inspect slotErrors; rows do not prove every requested booking is eligible or every free seat is independently counted |
| bookable_durations | Successful empty duration list for selected fixture | No nonempty fixture/UI duration comparison proved |
| enrollment_balance | One enrollment remaining-session bucket | UI fixture route crashed; balance comparison blocked; not a monthly booked/attended/overbooking report |
| recurring_series | Successful seed-appointment read | Direct recurring-ID-only lookup remains unsupported |
| attendance_statuses | Definitions returned | No-show appointment fixture matched UI; overall appointment can still be CONFIRMED |
| activity_logs | Successful empty selected historical window; separate saved historical service-event read | No controlled service edit; actor-name parity not fully verified |
| guardian_profile | Successful profile read | Exact primary guardian timezone and full audit timestamp UI comparison incomplete |
| student_audit | Successful read | Missing backend audit fields are not fabricated |
| record_metadata | Company and location reads succeeded | AutoInvites metadata readable, UI value not located/verified |
| instructor_services | Successful read and continuation | Not exhaustive schedule/assignment UI parity |
| consumer_appointment_count | Successful read | Undated count, not monthly enrollment usage |
| radius_student | Successful current projection | Not a sync-history or last-five-balances journal |

Existing employees/services pagination returned distinct pages. Short/full
company_settings were deep-equal; location_settings/apps/resources reads also
succeeded earlier. None of these earlier successes bypass the current blocker.

## Guardian status fix

- Replaced hard-coded active=true with QA frontend enrollment-window calculation.
- Traced release 3ffc4d0 helper 1975 and guardian-detail caller 4755.
- Preserved the frontend's mixed finite/open-ended OR behavior.
- Kept guardian badge separate from advance-booking eligibility.
- Failed/incomplete/out-of-group detail reads produce null/unknown, not active.
- 44 automated tests pass, including 21 cases executed against the original
  bundled frontend helper. Live patched guardian/UI parity remains pending.

Private saved responses remain in `/private/tmp/math-live-results.json` and
`/private/tmp/math-acceptance-agent/`; they are not committed.

## Host-environment retry and fresh UI check

Retried outside the sandbox with the supplied QA API key. The real local server
on port 8137 returned health 200 and completed MCP initialize/tools-list. Actual
MCP calls returned:

- find_guardian(parentId=Math Test company, name=Jacob Marlow): no matches with
  upstream 403 warning (not a no-match finding).
- get_entity(availability_rules, parentId=POD#A-Location-M1-B): failed, upstream
  403 Cloudflare HTML challenge.
- get_entity(availability_window, same location, Nov 12-13 2026): failed with
  the same challenge.

Fresh Chrome observations: Jacob detail shows Inactive. Availability for
POD#A-Location-M1-B loads Nov 8-14 2026 in Asia/Kolkata and shows, for example,
9am-1pm capacity 1, 1-4pm capacity 2, 4-6pm capacity 3, and 6-8pm capacity 4
blocks with five session types; Shashank test 1 has POD German 9am-5pm capacity 4
blocks. Thus browser UI works, but fresh API/MCP parity is still blocked.

Evidence: `/private/tmp/math-targeted-host-results.json`,
`/private/tmp/math-targeted-host-output.txt`, `/private/tmp/math-http-server.log`.
No browser credentials copied, no QA data edited, no push.

## Logged-in Chrome API verification (completed)

At 2026-11-12T18:02Z, executed read-only same-origin GraphQL requests in Chrome's
logged-in QA session. No cookies or tokens were extracted or added to MCP config.
All four requests returned HTTP 200 with no GraphQL errors:

- Scoped FindGuardianQuery: one Jacob Marlow record.
- CustomerDetailQuery: seven linked students with enrollment dates.
- SupportRead/openHourRules: 48 rules, hasNextPage=false.
- SupportRead/listOpenHourRulesForAvailability: nine rule groups for Nov 8-14
  Asia/Kolkata (UTC bounds Nov 7 18:30 through Nov 14 18:30).

Fed these fresh guardian responses through the actual local guardian domain
mapping with the network client replaced by recorded-response replay. It returned
one match, active=false, activeStatus=inactive. Independently reopened Jacob's
Chrome detail: Inactive, and all seven student badges Inactive. This verifies
live-data mapping/UI parity, not API-key-only HTTP MCP connectivity.

Availability UI comparison: Alyssa Olson has 28 weekly blocks, four per day:
09:00-13:00 capacity 1; 13:00-16:00 capacity 2; 16:00-18:00 capacity 3;
18:00-20:00 capacity 4. All match returned rule times after conversion to
Asia/Kolkata. Opened Sunday Nov 8 09:00-13:00 details: capacity 1, weekly Sunday,
and new-service-test, Sanskrit, Virtual service, TEST, POD German. Five returned
service IDs map to exactly those names using the earlier saved service catalog.
Compared that instructor's stored-rule and bounded-window blocks by ID: same 28
IDs and all common fields equal. Their array order differs; no ordering guarantee
was assumed. This is a sampled UI comparison, not an exhaustive nine-instructor
or bookable-slots eligibility audit.

Private evidence: `/Users/appointy/Downloads/qa-chrome-read-evidence.json`;
`/private/tmp/math-chrome-compare.py`;
`/private/tmp/math-chrome-guardian-mapped.json`.
API-key-only transport remains Cloudflare-blocked. No push or QA writes.

## Office-network API-key-only retry - 13 November 2026

Fresh host-run local HTTP MCP calls now succeed with the same supplied QA API
key, no browser credentials and no code/config change:

- Health 200; MCP handshake and seven-tool listing succeed.
- find_guardian(Jacob Marlow): one match, seven linked students,
  active=false, activeStatus=inactive, no warnings. Matches the previously
  inspected QA UI Inactive badge.
- availability_rules: success.
- availability_window (Nov 12-13): success with has_more=true and a cursor.
- Independent minimal AppQuery curl: HTTP 200, application/json, errors=null;
  cf-ray a59baaaf5e91f7e1-BOM; no cf-mitigated challenge header.

This supersedes the current-connectivity blocker above for these tested calls.
Earlier 403s were Cloudflare HTML challenges. The same key succeeding after the
network change supports an edge/network-policy explanation, not a lack of key
permissions on these queries. Exact Cloudflare rule attribution still requires
Cloudflare security-event inspection; IP reputation, bot scoring or network
routing are hypotheses, not confirmed causes. This does not establish access
for other previously unsupported APIs or solve separate GCP IAM restrictions.

Evidence: `/private/tmp/math-office-retest.txt`,
`/private/tmp/math-targeted-host-results.json`,
`/private/tmp/math-office-probe-headers.txt`. No push.
