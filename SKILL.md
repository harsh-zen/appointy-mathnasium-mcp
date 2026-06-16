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
- `mathnasium_search_logs`
- `mathnasium_get_log_search_result`

## When to use

Use this skill when a support workflow needs:

- center/company/location identification
- guardian account lookup
- student lookup and enrollment visibility
- mapping ticket text to valid Appointy entities
- log/sync investigation through the outsourced Codefac investigator

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
- plus at least one of `email`, `name`, `phone`
- optional `centerId` for extra narrowing

### `mathnasium_find_student`

Purpose:
- Find students directly at group scope and return enrollment-rich results.

Behavior:
- Group-level lookup (does not require center/company pre-scope).
- Best filters: `studentName`, `guardianId`, `centerId`.
- `guardianEmail` alone is weak; prefer `guardianId`.

### `mathnasium_search_logs`

Purpose:
- Start an outsourced log/sync investigation through the configured Codefac pipeline.
- Return the final report if it completes during the initial wait, otherwise return a `pipelineRunId` for later follow-up.

Use when:
- Appointy entity lookup is not enough and the ticket requires backend logs, sync investigation, or Radius/Appointy sync failure evidence.
- The user explicitly asks to check logs, sync logs, pipeline/sync failures, or why an entity did not sync.

Input:
- `prompt` is required and should be a natural-language investigation request with all known ticket context.
- Optional `timeoutSeconds` controls the initial wait window. Default is short enough for interactive use.

Behavior:
- The MCP adds instructions telling Codefac not to post to Slack and to return only the final investigation report as pipeline output.
- The tool polls during the initial wait window. If Codefac is still running, it returns `status: running` and a `pipelineRunId`.
- If Codefac returns `awaiting_input`, surface `pendingQuestions` to the user/agent.
- If Codefac returns `awaiting_credentials`, tell the operator that the Codefac provider sign-in/agent credentials need to be reconnected before log investigation can complete.

If response is `running`:
- Save the `pipelineRunId`.
- Tell the user/operator that log investigation has started and is still running.
- Call `mathnasium_get_log_search_result` later with the `pipelineRunId`.

### `mathnasium_get_log_search_result`

Purpose:
- Check a previously started Codefac log/sync investigation.

Input:
- `pipelineRunId` from `mathnasium_search_logs`.

Behavior:
- If completed, returns `status: success` and `output`.
- If still running, returns `status: running`.
- If failed or paused, returns the Codefac state and error/pending question details.

Do not use when:
- A simple center/guardian/student lookup can answer the ticket.
- The user is asking for writes or account changes.

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

For log search, return:

- Codefac run status and `pipelineRunId`
- final investigation report if completed
- `running` status plus `pipelineRunId` if the investigation is still in progress
- pending questions if Codefac asks for input
- credential reconnect message if Codefac returns `awaiting_credentials`
- error message if the run failed or cannot be checked

## Scope and safety

- This skill is for data lookup only (read workflows).
- Do not infer write/mutation actions from these tools.
- Treat lookup results as evidence to guide support replies and escalations.
