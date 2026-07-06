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

- `MATHNASIUM_COMPANY_ID_OPTIONAL`
- `DEFAULT_SUPPORT_USER_ID`
- `DEFAULT_FIRST` (default `25`)
- `GROUP_CONTEXT_CACHE_TTL_SECONDS` (default `900`)
- `APPOINTY_TIMEOUT_SECONDS` (default `20`)
- `ENABLE_PII_MASKING` (default `false`)
- `APPOINTY_BOOKING_URL_TEMPLATE` (default `https://www.appointy.com/{locationSlug}`)
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` (preferred deployed secret containing the service account JSON)
- `GOOGLE_APPLICATION_CREDENTIALS` (local path to service account key, or use ADC/workload identity)
- `GCP_PROJECT_ID` (default `waqt-prod`)
- `GCP_LOG_LOCATION` (default `europe-west1-c`)
- `GCP_CLUSTER_NAME` (default `mathphase2-prod-gke`)
- `GCP_NAMESPACE` (default `prod`)
- `GCP_POD_APP_LABEL` (default `deployment`)
- `GCP_LOG_DEFAULT_LOOKBACK_HOURS` (default `48`)
- `GCP_LOG_MAX_LIMIT` (default `200`)

## Tool Input Notes

- `mathnasium_find_guardian`
  - Requires `parentId` (`companyId` or `locationId`).
  - Searches only inside that scope (no cross-company scan).
  - Accepts at least one of: `email`, `name`, `phone`.
- `mathnasium_find_student`
  - Uses group-level student search (`MATHNASIUM_GROUP_ID`) directly.
  - `guardianId` is supported as a direct filter.
  - `guardianEmail` is only a hint and is ignored unless `guardianId` is also provided.
- `mathnasium_get_entity`
  - Use for exact scoped reads of entities not covered by center/guardian/student tools.
  - Supported `entityType` values: `appointments`, `services`, `employees`, `resources`, `group_settings`, `company_settings`, `location_settings`, `apps`.
  - For `appointments`, `services`, and `resources`, pass a location-level `parentId`.
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
  -e MATHNASIUM_COMPANY_ID_OPTIONAL \
  -e GOOGLE_APPLICATION_CREDENTIALS_JSON \
  -e GOOGLE_APPLICATION_CREDENTIALS \
  -e GCP_PROJECT_ID \
  appointy-mathnasium-mcp
```
