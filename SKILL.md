---
name: mathnasium-support-data-lookup
description: Use this skill for Mathnasium support data lookup through the Appointy MCP tools. Handles center, guardian, and student discovery with strict scope rules. Use this when resolving support tickets that need account/entity lookup, especially guardian lookup that requires company/location scope from center search first.
metadata:
  short-description: Mathnasium support lookup flow
---

# Mathnasium Support Data Lookup

This skill is for read-only support lookup using these MCP tools:

- `mathnasium_get_group_context`
- `mathnasium_find_center`
- `mathnasium_find_guardian`
- `mathnasium_find_student`
- `mathnasium_get_entity`
- `mathnasium_search_custom_logs`

## When to use

Use this skill when a support workflow needs:

- center/company/location identification
- guardian account lookup
- student lookup and enrollment visibility
- appointments, services/session types, instructors/employees, resources, settings, or app-module lookup
- mapping ticket text to valid Appointy entities
- production GCP log retrieval for Radius/Appointy sync investigation
- custom production log search by exact queryId, path, error text, or exact log text supplied in the request

## Tool contracts

### `mathnasium_get_group_context`

Purpose:
- Load group structure, companies, locations, aliases, and cached center metadata.

Use when:
- starting a new investigation
- you need canonical center/company IDs
- you need booking URL or slug context

### `mathnasium_find_center`

Purpose:
- Resolve center/company/location from free-text hints.

Common hints:
- center name
- city
- booking URL or slug
- custom location id

Output to capture for next steps:
- `companyId`
- `locationId`
- `centerName`
- `bookingUrl`
- `active`

### `mathnasium_find_guardian`

Purpose:
- Find guardian records in a specific parent scope.

Hard requirement:
- `parentId` is required.
- `parentId` must be company or location scope (`com_...`, `loc_...`, or full path).
- No cross-company/global guardian scan.

Input:
- `parentId` (required)
- plus at least one of `email`, `name`, `firstName`, `lastName`, `phone`
- optional `centerId` for extra narrowing
- use `firstName` and `lastName` when the requester provides separated name parts; use `name` for a full/partial name string

### `mathnasium_find_student`

Purpose:
- Find students directly at group scope and return enrollment-rich results.

Behavior:
- Group-level lookup (does not require center/company pre-scope).
- Best filters: `studentName`, `guardianId`, `centerId`.
- `guardianEmail` alone is weak; prefer `guardianId`.


### `mathnasium_get_entity`

Purpose:
- Common read-only lookup for exact scoped entities not covered by the dedicated center/guardian/student tools.
- Use this for Appointy objects like appointments, services/session types, employees/instructors, resources, settings, and apps.

Supported `entityType` values:
- `appointments`
- `services`
- `employees`
- `resources`
- `group_settings`
- `company_settings`
- `location_settings`
- `apps`

Scope rules:
- For `appointments`, `services`, and `resources`, provide a location-level `parentId`.
- For `employees`, provide a company-level `parentId`.
- For `company_settings` and `apps`, provide `companyId`.
- For `location_settings`, provide both `companyId` and `locationId`.
- For `group_settings`, no scope ID is needed.

Optional exact filter:
- `entityId` filters exact IDs from returned list results.
- Do not use this tool for fuzzy name matching.
- Do not use this tool to find centers, guardians, or students. Use the dedicated tools for those.

Returns:
- `items` for list-like entities (`appointments`, `services`, `employees`, `resources`).
- `data` for settings/app entities.
- `source`, showing the internal GraphQL query used.

Examples:
- To inspect appointments at a center: use `entityType="appointments"` and `parentId=<locationId>`.
- To inspect session types at a center: use `entityType="services"` and `parentId=<locationId>`.
- To inspect instructors for a center owner: use `entityType="employees"` and `parentId=<companyId>`.
- To inspect center settings: use `entityType="location_settings"`, `companyId=<companyId>`, and `locationId=<locationId>`.

### `mathnasium_search_custom_logs`

Purpose:
- Search Mathnasium production GKE logs using custom filters without writing raw Cloud Logging syntax.
- Use this for all log investigations, including Radius wrapper sync logs, GraphQL/queryId logs, Admin request logs, and exact log/error text supplied in the request.

Use when:
- The support request mentions a frontend/backend GraphQL `queryId`.
- You need Admin request logs for a path or status code.
- The request provides an exact log phrase, error text, endpoint fragment, or payload clue.
- You need to search a specific error text, endpoint name, entity ID, or mixed set of terms.

Source presets:
- `all`: no source-specific preset beyond Mathnasium GKE app logs.
- `admin_requests`: filters to `mathnasium-admin.appointy.com` request logs.
- `graphql`: filters toward GraphQL finished/error request logs.
- `radius_wrappers`: filters toward wrapper `Successful`/`Failed` logs.

Inputs:
- `textTerms`: exact text snippets, error messages, or payload clues.
- `identifiers`: emails, Appointy IDs, Radius IDs, custom IDs, names, etc.
- `messages`: exact `jsonPayload.message` values such as `Finished request` or `Error while processing request`.
- `queryIds`: GraphQL operation/query IDs such as `CompanyAppointmentReportQuery`.
- `paths`: request path fragments such as `/graphql` or `/api/v1/...`.
- `endpointNames`: endpoint fragments such as `customer-account`.
- `statusCodes`: status text/values when present in payloads.
- `matchAllTerms`: set true when every provided text/path/id/query term must be present.

Examples:
- Radius wrapper sync trace: `source="radius_wrappers"`, `identifiers=["guardian@email.com"]`, `endpointNames=["customer-account"]`, include timeframe.
- GraphQL query trace: `source="graphql"`, `queryIds=["AppointmentQuery"]`, include timeframe.
- Admin path trace: `source="admin_requests"`, `paths=["/graphql"]`, `statusCodes=["403"]`, include timeframe.
- Exact text search: `source="all"`, `textTerms=["Total number of rows"]`, add identifiers/timeframe.

Investigation tip:
- If recent logs show success but the user reported missing data, search farther back for earlier failures and mention both in the support report.

## Required support flow

### Guardian lookup flow (mandatory)

1. Extract center hint from ticket/request.
2. Run `mathnasium_find_center` to resolve candidate center(s).
3. Select the best candidate and get `companyId` or `locationId`.
4. Run `mathnasium_find_guardian` with that ID as `parentId`.
5. Validate guardian `centerIds` and linked `studentIds/students`.

If no center/location hint is present:
- Ask user/customer for one of: center name, booking URL, location ID, or city+center.
- Do not run blind guardian lookup.

### Student lookup flow

1. Run `mathnasium_find_student` with `studentName` and/or `guardianId`.
2. If multiple matches, narrow with `centerId` and guardian linkage.
3. Use enrollments and status fields for support reasoning.

### Other entity lookup flow

1. If the request is about appointments, session types, instructors, resources, settings, or app modules, use `mathnasium_get_entity`.
2. First obtain the exact `companyId` or `locationId` using `mathnasium_find_center` if needed.
3. Call `mathnasium_get_entity` with the explicit `entityType` and required scope ID.
4. If the support request only has a vague name and no center/company context, ask for the missing scope before calling the tool.
5. Do not use `mathnasium_get_entity` for guardian/student/center search.

### Log lookup flow

1. Extract identifiers and timeframe from the Slack/ticket request.
2. Resolve extra IDs with center/guardian/student tools if useful.
3. For Radius wrapper sync failures, call `mathnasium_search_custom_logs` with `source="radius_wrappers"`.
4. For GraphQL/queryId/path/exact-text investigations, call `mathnasium_search_custom_logs` with the appropriate source preset.
5. If current-window logs show success but the issue says data was missing, search farther back for earlier failures.
6. Use the returned logs as evidence for the final support explanation.

## Disambiguation rules

- If multiple centers match: ask a center confirmation question before guardian lookup.
- If multiple guardians/students match: ask for one more identifier (email, phone, guardian ID, center).
- If entity is inactive: report it explicitly and continue lookup with active candidates if available.

## Output expectations for support use

For each lookup, return a compact support summary:

- selected entity IDs (`companyId`, `locationId`, `guardianId`, `studentId`)
- confidence signal (`single clear match` vs `multiple candidates`)
- blocking gaps (`missing center hint`, `ambiguous guardian`, etc.)
- next required input, if any

For log lookup, return:

- identifiers searched
- timeframe searched
- count of matching log entries and message/severity summary
- relevant errors or dropped payload clues
- whether a broader/earlier search is needed

## Scope and safety

- This skill is for data lookup only (read workflows).
- Do not infer write/mutation actions from these tools.
- Treat lookup results as evidence to guide support replies and escalations.
