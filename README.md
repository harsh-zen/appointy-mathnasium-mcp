# Appointy Mathnasium MCP Server

Support-native MCP server for Mathnasium Appointy core lookup workflows.

## Experimental Warning

This MCP is an experimental support automation PoC.
It is intentionally built on top of existing Appointy APIs as-is, without changing existing APIs and without introducing new backend wrapper endpoints.
Behavior and response shapes can evolve as the underlying APIs evolve.

## P0 Tools Implemented:

- `mathnasium_get_group_context`
- `mathnasium_find_center`
- `mathnasium_find_guardian`
- `mathnasium_find_student`
- `mathnasium_get_entity`
- `mathnasium_find_appointments`
- `mathnasium_search_custom_logs`

## Data Source Notes:

- `mathnasium_get_group_context` uses GraphQL `AppQuery`.
- `mathnasium_find_center` uses cached GraphQL context index.
- `mathnasium_find_guardian` is GraphQL-first (`customers`) with guardian-student enrichment from `CustomerDetailQuery`.
- `mathnasium_find_student` uses verified group-scoped `mathnasiumSearchEntity(type: Student)` and hydrates validated IDs; guardian-scoped reads retain `students(guardianId: ...)`.
- `mathnasium_get_entity` is a common read-only entity lookup for objects not covered by the first-class center/guardian/student tools.
- Guardian and student responses include enrollment-rich fields where available (`enrollments`, membership/session details, delivery methods, holds).
- `mathnasium_search_custom_logs` searches the same production GKE logs using custom text, queryId, path, message, and endpoint filters without exposing raw Cloud Logging syntax.

## Environment Variables

Required:

- `APPOINTY_API_BASE_URL`
- `APPOINTY_API_KEY`
- `MATHNASIUM_GROUP_ID`

Optional:

- `DEFAULT_SUPPORT_USER_ID`
- `DEFAULT_FIRST` (default `25`)
- `GROUP_CONTEXT_CACHE_TTL_SECONDS` (default `900`)
- `APPOINTY_TIMEOUT_SECONDS` (default `20`)
- `ENABLE_PII_MASKING` (default `false`)
- `APPOINTY_BOOKING_URL_TEMPLATE` (default `https://mathnasium-booking.appointy.com/{locationSlug}`)
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` (preferred deployed secret containing the service account JSON)
- `GOOGLE_APPLICATION_CREDENTIALS` (local path to service account key, or use ADC/workload identity)
- `GCP_PROJECT_ID` (default `waqt-prod`)
- `GCP_LOG_LOCATION` (default `europe-west1-c`)
- `GCP_CLUSTER_NAME` (default `mathphase2-prod-gke`)
- `GCP_NAMESPACE` (default `prod`)
- `GCP_POD_APP_LABEL` (default `deployment`)
- `GCP_LOG_DEFAULT_LOOKBACK_HOURS` (default `48`)
- `GCP_LOG_MAX_LIMIT` (default `200`)
- `GCP_LOG_CHUNK_HOURS` (default `48`)
- `GCP_LOG_QUERY_TIMEOUT_SECONDS` (default `20` per chunk)
- `GCP_LOG_TOTAL_TIMEOUT_SECONDS` (default `45`; effective application cap is `25` seconds)
- `GCP_LOG_MAX_ATTEMPTS` (default `2` per chunk)
- `GCP_LOG_RETRY_BACKOFF_SECONDS` (default `1`)

## Tool Input Notes

- `mathnasium_find_guardian`
  - Requires `parentId` (`companyId` or `locationId`).
  - Searches only inside that scope (no cross-company scan).
  - Accepts at least one of: `email`, `name`, `firstName`, `lastName`, `phone`.
  - `name` can be a full/partial name; `firstName` and `lastName` are available when the agent has separated name parts.
- `mathnasium_find_student`
  - Uses group-level student search (`MATHNASIUM_GROUP_ID`) directly.
  - `guardianId` is supported as a direct filter.
  - `guardianEmail` is only a hint and is ignored unless `guardianId` is also provided.
- `mathnasium_get_entity`
  - Use for exact scoped reads of entities not covered by center/guardian/student tools.
  - Supported `entityType` values: `appointments`, `services`, `employees`, `resources`, `group_settings`, `company_settings`, `location_settings`, `apps`.
  - For `appointments`, `services`, and `resources`, pass a location-level `parentId`.
  - `services` returns session-type linkage data: `membershipTypeIds`, `gradeRangeIds`, linked names, durations in seconds/minutes, active status, and booking-rule metadata. This lets support compare a student's enrollment IDs with the session types configured at that center.
  - For `employees`, pass a company-level `parentId`.
  - For `company_settings` and `apps`, pass `companyId`.
  - For `location_settings`, pass both `companyId` and `locationId`.
  - Optional `entityId` filters exact IDs from returned list results; no fuzzy name matching is performed.
  - This intentionally does not replace `mathnasium_find_center`, `mathnasium_find_guardian`, or `mathnasium_find_student`.
- `mathnasium_search_custom_logs`
  - Use for non-standard log investigations where the agent already has exact terms, query IDs, request paths, endpoint names, or error/message text.
  - `source` can be `all`, `admin_requests`, `graphql`, or `radius_wrappers`.
  - Accepts `textTerms`, `identifiers`, `messages`, `queryIds`, `paths`, `endpointNames`, `statusCodes`, ISO `startTime`/`endTime`, and `matchAllTerms`.
  - For Radius wrapper sync logs, use `source="radius_wrappers"` with identifiers and optional `endpointNames` such as `customer-account`, `student`, or `appointment`.
  - Requires at least one meaningful filter; it will not run a broad unfiltered production log scan.
  - Long date ranges are searched sequentially in newest-first 48-hour chunks. Results are deduplicated and share one global limit.
  - Raw payloads are automatically omitted for long-range searches. After finding relevant timestamps, rerun a 48-hour-or-shorter window with `includePayload=true`.

Transport/runtime (optional):

- `MCP_TRANSPORT` (`stdio` by default, supports `sse`, `streamable-http`)
- `MCP_HOST` (default `127.0.0.1`)
- `MCP_PORT` (default `8010`)
- `MCP_STREAMABLE_HTTP_PATH` (default `/mcp`)
- `MCP_SSE_PATH` (default `/sse`)
- `MCP_JSON_RESPONSE` (default `false`)
- `MCP_STATELESS_HTTP` (default `false`)
- `MCP_LOG_LEVEL` (default `INFO`)

## Local Run

```bash
cd appointy_mathnasium_mcp
uv run appointy-mathnasium-mcp --transport stdio
```

For remote transport:

```bash
cd appointy_mathnasium_mcp
uv run appointy-mathnasium-mcp --transport streamable-http --host 0.0.0.0 --port 8010
```

Health endpoint:

- `GET /health`

## Docker

Build:

```bash
docker build -t appointy-mathnasium-mcp .
```

Run (uses existing env vars):

```bash
docker run --rm -p 8080:8080 \
  -e APPOINTY_API_BASE_URL \
  -e APPOINTY_API_KEY \
  -e MATHNASIUM_GROUP_ID \
  -e GOOGLE_APPLICATION_CREDENTIALS_JSON \
  -e GOOGLE_APPLICATION_CREDENTIALS \
  -e GCP_PROJECT_ID \
  appointy-mathnasium-mcp
```
## Verified Support Reads (API key)

The support additions use existing GraphQL reads, not new Appointy backend endpoints.
`mathnasium_get_entity` accepts these additional exact `entityType` values:

| Type | Required arguments | Meaning / limits |
| --- | --- | --- |
| `booking_rules` | location `parentId` | Location rules; optional `serviceId` reads the service override. Interpret `policyType` before interval values. |
| `portal_settings` | location `parentId` | Guardian portal/booking and recurring-booking toggles. |
| `availability_rules` | location `parentId` | Configured current/expired blocks, recurrence, services, resources and capacity; native cursor. |
| `availability_window` | location `parentId`, `startFrom`, `startTo` | Rules intersecting a window up to 31 days; bounded local continuation. |
| `bookable_slots` | location `parentId`, `studentId`, `enrollmentId`, `serviceId`, `durationSeconds`, dates | Existing slot and eligible-service results; at most 7 days. Empty slots are not a complete diagnosis. |
| `bookable_durations` | location `parentId`, `studentId`, `serviceId`, dates | Durations in seconds; at most 7 days. |
| `enrollment_balance` | `studentId`, `guardianId` | Monthly remaining-bookable buckets; set the actual `timezone`. Not attendance counts or Radius history. |
| `recurring_series` | seed appointment `entityId` | Series occurrences and recurrence rule. Direct `rec_` ID lookup is not available with the key. |
| `attendance_statuses` | location `parentId` | Custom attendance names/IDs such as No-show, separate from overall appointment status. |
| `activity_logs` | `parentId`, dates | Audit evidence up to 90 days; optional exact `eventIds`; offset wrapped in a filter-bound cursor. Deleted snapshots can be incomplete. |
| `guardian_profile` | guardian `entityId` | Stored profile timezone and available audit dates. |
| `student_audit` | student `entityId` | Explicit audit field-mask read. |
| `record_metadata` | `companyId`, optional `locationId` | Raw and decoded metadata, including separately stored AutoInvites; unknown timestamps remain null. |
| `instructor_services` | location `parentId`, `instructorId` | Assigned services with native pagination. |
| `consumer_appointment_count` | location `parentId`, `studentId` or `guardianId` | Undated upstream counter, not a monthly usage report. |
| `radius_student` | Radius student ID in `entityId` | Current wrapper projection, not last received payload/history. |

Use full IDs returned by lookup. Short company IDs are supported; short location IDs
need a company or a unique center-context match. Never substitute IDs from another group.
For list reads, follow `next_cursor` with identical filters until `has_more=false`.
The local continuation used for slots/window reads re-fetches the bounded window; it
is not a snapshot and results can move if availability changes.

`employees` now includes roles with their applicable scope, module names, location
assignments and profile timezone. `employees` and `services` paginate with native cursors.
Settings lookups accept short/full company/location IDs and fall back to a direct read
when an otherwise valid record is absent from cached group context.

### Filtered appointments

Use `mathnasium_find_appointments` (or `get_entity` type `appointments` with
`studentId`/`guardianId`, `startFrom`/`startTo`, `parentId` and `cursor`).
Student, booking-customer, date and overall status filters execute upstream.
The dedicated tool also accepts `custom_status_ids` from `attendance_statuses`.
Default order is newest first; `order=asc` is supported. At most 50 rows per page,
with a native filter-bound continuation. A location alone is rejected; provide an
identity or a positive date window no longer than 62 days. When dates are omitted
with an identity, the default is 31 days before through 31 days after now.
An overall `APPOINTMENT_*` status is not an attendance label. Creator IDs do not
by themselves identify a Radius sync. History is evidence, not a fabricated actor/source.

### Log search continuation

`mathnasium_search_custom_logs` reads one native GCP page (up to 50 rows) before
returning, and scans empty newest-first chunks within a hard application budget of
at most 25 seconds. The GCP RPC has an explicit timeout and automatic SDK retries
are disabled; application retry attempts remain bounded by that deadline.
Use `cursor` with the identical arguments for `next_cursor`. A timed-out chunk
returns `partial=true`, a reason and a retryable continuation, not an empty success.
`summaryOnly=true` omits rows and returns **page-level** counts/latest error, not a
full-window aggregate. A partial/limited search never proves that no request exists.
Infrastructure/proxy 503s outside the application cannot be guaranteed absent.
Name/identifier search retains existing text-match semantics; exact structured-field
indexing is not claimed by these changes.

### Excluded backend gaps

No utilization/overbooking/notification report access, direct recurring-ID reads,
provider delivery/suppression, sync/balance history, complete deleted-availability
snapshots or authoritative all-reasons eligibility endpoint is added. Null audit
fields remain unknown. There are no writes, new authentication settings or deployment changes.
