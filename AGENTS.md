# Appointy Mathnasium MCP Agent Guide

This repo contains a read-only Mathnasium support MCP server. Before changing code, keep the public tool contract stable unless the user explicitly asks to change it.

## Working Rules

- Do not push without explicit user permission.
- Do not include `.bifrost.yaml` unless the user explicitly asks for deployment config changes.
- Keep this MCP read-only. Do not add create/update/delete/write tools without explicit approval and a human-approval design.
- Preserve the existing six public tools unless the user asks otherwise:
  - `mathnasium_get_group_context`
  - `mathnasium_find_center`
  - `mathnasium_find_guardian`
  - `mathnasium_find_student`
  - `mathnasium_get_entity`
  - `mathnasium_search_custom_logs`
- Guardian lookup must remain scoped. Never add a blind/global guardian scan.
- `MATHNASIUM_COMPANY_ID_OPTIONAL` was intentionally removed. Do not reintroduce it.

## Architecture Map

The code is split by responsibility:

- `src/appointy_mathnasium_mcp/server.py`
  - Process entrypoint.
  - Registers `/health`.
  - Starts stdio/SSE/streamable HTTP transport.
  - Imports `tools.py` for MCP tool registration.

- `src/appointy_mathnasium_mcp/app.py`
  - Creates the shared `FastMCP` instance.
  - Owns MCP host/port/path/log-level wiring.

- `src/appointy_mathnasium_mcp/config.py`
  - Reads environment variables.
  - Contains config defaults and validation helpers.
  - Add new env vars here first, then document them in `README.md`.

- `src/appointy_mathnasium_mcp/tools.py`
  - Public MCP tool layer.
  - Keep this thin: validate config, define MCP arguments/descriptions, call domain/log internals, return MCP-friendly dicts.
  - Use `typing.Annotated` plus `pydantic.Field(description=...)` for all new tool args so MCP clients see useful schemas.

- `src/appointy_mathnasium_mcp/domain.py`
  - Business/support lookup behavior.
  - Contains center, guardian, student, enrollment, and common entity normalization.
  - Put support-specific logic here, not in `tools.py`.

- `src/appointy_mathnasium_mcp/clients.py`
  - External API clients.
  - Contains Appointy HTTP/GraphQL calls and GCP Logging client.
  - Do not put support reasoning here.

- `src/appointy_mathnasium_mcp/queries.py`
  - GraphQL query strings only.
  - Add or modify GraphQL fields here before touching parsing logic.

- `src/appointy_mathnasium_mcp/log_search.py`
  - GCP log filter construction and log result shaping.
  - Add new log presets here.

- `src/appointy_mathnasium_mcp/utils.py`
  - Generic helpers only: normalization, parsing, masking, date helpers, dedupe helpers.

- `src/appointy_mathnasium_mcp/errors.py`
  - Shared custom exceptions.

- `tests/`
  - Unit/regression tests. Add tests for every non-trivial behavior change.

## How To Add A New MCP Tool

1. Decide if it really needs to be a new public tool.
   - Prefer extending `mathnasium_get_entity` for exact scoped read-only entities.
   - Prefer extending `mathnasium_search_custom_logs` for log-search variants.
   - Only add a new first-class tool when the agent needs a distinct support workflow or strongly typed contract.

2. Add API/query support.
   - For GraphQL, add the query to `queries.py`.
   - For REST/GraphQL call wiring, add a method in `clients.py`.

3. Add support behavior in `domain.py` or `log_search.py`.
   - Normalize raw Appointy/GCP data into support-friendly shapes.
   - Keep raw endpoint quirks hidden from MCP callers.
   - Include warnings when results are partial, ambiguous, or scope is missing.

4. Register the MCP tool in `tools.py`.
   - Use `@mcp.tool()`.
   - Use clear argument names that match support language.
   - Use `Annotated[..., Field(description="...")]` for every argument.
   - Keep the function body small and delegate to internals.

5. Document usage.
   - Update `README.md` for environment/tool behavior if needed.
   - Update `SKILL.md` if agent workflow guidance changes.

6. Test it.
   - Add unit tests for pure behavior.
   - For API-backed tools, add tests around parsing/normalization and config failure behavior.
   - Run:
     ```bash
     PYTHONPATH=src python3 -m unittest discover -s tests -v
     python3 -m py_compile src/appointy_mathnasium_mcp/*.py tests/*.py
     ```

7. If changing MCP schema, inspect registered tools locally:
   ```bash
   PYTHONPATH=src python3 - <<'PY'
   import appointy_mathnasium_mcp.server
   from appointy_mathnasium_mcp.app import mcp
   tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
   for name, tool in sorted(tools.items()):
       print(name)
       print(tool.parameters)
       print()
   PY
   ```

## How To Extend Existing Tools

### `mathnasium_find_guardian`

- Must require `parentId`.
- `parentId` must be a company/location scope from center lookup.
- Keep no-global-scan behavior.
- Name lookup supports:
  - `name`
  - `firstName`
  - `lastName`
- If Appointy search behavior changes, update `domain._find_guardians_internal()` and tests.

### `mathnasium_find_student`

- Group-scoped lookup.
- Does not require center/company first.
- `guardianEmail` alone is weak; prefer `guardianId`.
- Enrollment status is derived from enrollments, not raw Appointy active membership.

### `mathnasium_get_entity`

Use this for exact scoped reads that are not centers/guardians/students.

Supported entity types currently:

- `appointments`
- `services`
- `employees`
- `resources`
- `group_settings`
- `company_settings`
- `location_settings`
- `apps`

Scope rules:

- `appointments`, `services`, `resources`: location-level `parentId`
- `employees`: company-level `parentId`
- `company_settings`, `apps`: `companyId`
- `location_settings`: `companyId` and `locationId`
- `group_settings`: no scope id

### `mathnasium_search_custom_logs`

- Keep broad unfiltered scans blocked.
- Use source presets when possible:
  - `radius_wrappers`
  - `graphql`
  - `admin_requests`
  - `all`
- If adding a new source preset, update both `log_search.py` and the `source` Literal in `tools.py`.

## E2E Smoke Test

Use QA env unless the user explicitly asks for another environment.

```bash
export APPOINTY_API_BASE_URL="https://qa-mathnasium-admin.appointy.com"
export APPOINTY_API_KEY="<qa-api-key>"
export MATHNASIUM_GROUP_ID="grp_01HA9WW1JPRN80YE0DS6ZJJN88"
export DEFAULT_SUPPORT_USER_ID="usr_01HA9WQDFN3RYY1GJRVM0CGPV2"
export APPOINTY_BOOKING_URL_TEMPLATE="https://mathnasium-booking.appointy.com/{locationSlug}"

PYTHONPATH=src python3 -m appointy_mathnasium_mcp.server \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8137
```

Health:

```bash
curl http://127.0.0.1:8137/health
```

Expected:

- `/health` returns HTTP 200.
- MCP lists all six tools.
- `mathnasium_get_group_context` returns `status: success`.
- `mathnasium_find_center` returns center matches.
- `mathnasium_get_entity` can fetch scoped services for a location.
- `mathnasium_find_guardian` rejects missing `parentId` at schema/tool validation.
- `mathnasium_search_custom_logs` rejects unfiltered broad scans.

## Review Checklist

Before committing:

- Tool list still has expected public tools unless intentionally changed.
- No raw global guardian search was introduced.
- No write/mutation tool was introduced.
- No `MATHNASIUM_COMPANY_ID_OPTIONAL` was reintroduced.
- Tests pass.
- Compile passes.
- Docs/skill updated if workflow changed.
