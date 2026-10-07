import type { ReconcileRow } from './types'

export function filterReconcileRows(
  rows: ReconcileRow[],
  statusFilter: string,
  buildingFilter: string,
  categoryFilter = '',
): ReconcileRow[] {
  return rows.filter((row) => {
    if (statusFilter && row.status !== statusFilter) return false
    if (buildingFilter && row.expected_building !== buildingFilter) return false
    if (categoryFilter && row.category !== categoryFilter) return false
    return true
  })
}
