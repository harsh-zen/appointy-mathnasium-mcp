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
- `mathnasium_search_custom_logs`

## Data Source Notes:

- `mathnasium_get_group_context` uses GraphQL `AppQuery`.
- `mathnasium_find_center` uses cached GraphQL context index.
- `mathnasium_find_guardian` is GraphQL-first (`customers`) with guardian-student enrichment from `CustomerDetailQuery`.
- `mathnasium_find_student` is GraphQL-first (`students`) with single-student enrichment from `student(id: ...)`.
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
- `GCP_LOG_TOTAL_TIMEOUT_SECONDS` (default `45` per MCP call)
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
# Appointment lookup (experimental)

`mathnasium_find_appointments` searches the GraphQL appointment calendar by a bounded start-time window and optional center, student, guardian, status, or recurring-series filters. Supply both `start_from` and `start_to` as timezone-aware ISO 8601 timestamps (at most 62 days); without dates, an entity ID search uses a 62-day window centered on the current time. A center ID alone is not enough. The default page size is 25 (maximum 50); pass `next_cursor` as `cursor` for another page.

The upstream calendar query is scoped by time and parent. Student, guardian, status, and recurring-series filters, ordering, and paging are applied by this MCP after retrieval. This is not a server-side index or a stable snapshot: changes between page calls can shift results. If no `location_id` is given, the group is used as the calendar parent; verify that group-scoped calendar access is supported before relying on this path in production. `cancelled_at` is omitted because the captured GraphQL query does not expose a verified cancellation timestamp.
