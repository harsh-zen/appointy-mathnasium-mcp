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
- `mathnasium_search_gcp_logs`

## Data Source Notes

- `mathnasium_get_group_context` uses GraphQL `AppQuery`.
- `mathnasium_find_center` uses cached GraphQL context index.
- `mathnasium_find_guardian` is GraphQL-first (`customers`) with guardian-student enrichment from `CustomerDetailQuery`.
- `mathnasium_find_student` is GraphQL-first (`students`) with single-student enrichment from `student(id: ...)`.
- Guardian and student responses include enrollment-rich fields where available (`enrollments`, membership/session details, delivery methods, holds).
- `mathnasium_search_gcp_logs` uses Google Cloud Logging to search Appointy M production GKE logs for Mathnasium Radius wrapper activity.

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
- `mathnasium_search_gcp_logs`
  - Requires `identifiers` such as guardian/student email, Radius ID, custom ID, Appointy ID, company/location ID, or endpoint text.
  - Accepts optional `startTime` and `endTime` as ISO timestamps; defaults to the last configured lookback window.
  - Defaults to `Successful` and `Failed` wrapper log messages.
  - Returns matching raw/structured log entries and summary counts; the agent performs diagnosis using the logs.

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
