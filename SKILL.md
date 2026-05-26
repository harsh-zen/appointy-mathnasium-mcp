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

## When to use

Use this skill when a support workflow needs:

- center/company/location identification
- guardian account lookup
- student lookup and enrollment visibility
- mapping ticket text to valid Appointy entities

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

## Scope and safety

- This skill is for data lookup only (read workflows).
- Do not infer write/mutation actions from these tools.
- Treat lookup results as evidence to guide support replies and escalations.
