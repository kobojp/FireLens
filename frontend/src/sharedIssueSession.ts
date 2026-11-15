import type { SharedIssueStatus } from './types'

/** Retain the most recent explicit sync response per root for this app run only. */
const lastExplicitSync = new Map<number, SharedIssueStatus>()

export function rememberSharedIssueSync(result: SharedIssueStatus) {
  lastExplicitSync.set(result.root_id, result)
}

export function previousSharedIssueSync(rootId: number | null): SharedIssueStatus | null {
  return rootId === null ? null : lastExplicitSync.get(rootId) ?? null
}
