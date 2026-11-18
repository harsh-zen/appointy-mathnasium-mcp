# Enrollment Sync Investigation

Use `mathnasium_get_enrollment_sync_history` for Radius enrollment balance
investigations. General GCP log search is unchanged.

1. Resolve the student and enrollment with `mathnasium_find_student`. Use the
   exact Radius `customEnrolmentId` as `radiusEnrollmentId`, not the Appointy ID.
2. Search the incident time first. Pass `startTime` and `endTime` with offsets
   (inclusive start, exclusive end), at most one hour per call and within the
   last 30 days. Work backwards in adjacent windows as needed. Use `limit` 1-25.
3. Follow `next_cursor` with identical arguments before declaring a window
   exhausted. Continue even if one page is empty and has a cursor. Report
   searched windows and disclose timeouts, unreadable rows and remaining pages.
4. Compare three things separately: most recent observed incoming balance
   (`receivedBalance`), latest known successful wrapper response balance
   (`successfulResponseBalance`), and any later failure. Use
   `enrollmentUpdateReported` to distinguish an explicit update marker
   from a balance merely included in the response. Do not label either as
   independently confirmed database commit. The current booking balance is a
   separate read.
5. Present up to five observed changes in successful response balances. Compare
   successive known values chronologically and collapse consecutive repeats.
   Do not count the earliest observation as a change without a baseline.
   Do not infer transitions across unknown values or unsearched gaps.
6. Report `observedAt` as the log time; it is not a separate receipt or commit
   time. Use `requestId` only when present. `logInsertId` identifies a log entry,
   not a source request or retry. No retry-level deduplication is guaranteed.
7. Missing values are unknown, not zero. No events in a window is not proof
   that Radius never sent the enrollment. This search covers student PUT
   outcome logs only and does not establish a complete 30-day history.
