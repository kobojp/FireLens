import type { ReconcileRow } from './types'

export function filterReconcileRows(
  rows: ReconcileRow[],
  classificationFilter: string,
  sectionFilter: string,
  categoryFilter = '',
  missingOnly = false,
  missingSlot = '',
): ReconcileRow[] {
  return rows.filter((row) => {
    if (classificationFilter && row.classification !== classificationFilter) return false
    if (sectionFilter && row.section !== sectionFilter) return false
    if (categoryFilter && row.category !== categoryFilter) return false
    if (missingOnly && row.classification === 'complete') return false
    if (missingSlot && !row.missing_slots.includes(missingSlot)) return false
    return true
  })
}
