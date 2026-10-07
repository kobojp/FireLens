import { describe, expect, it } from 'vitest'
import { filterReconcileRows } from './reconcile'
import type { ReconcileRow } from './types'

const rows: ReconcileRow[] = [
  {
    kind: 'ledger', category: 'extinguisher', row_no: 1, section: '第一門診1F', expected_building: '一門診',
    device_no: '一-01-01', specification: '10P', last_replacement_date: '', status: 'complete',
    found: [], missing_slots: [], naming_suggestions: [], near_candidates: [], marked_reshot: false,
  },
  {
    kind: 'ledger', category: 'extinguisher', row_no: 2, section: '中正樓1F', expected_building: '中正樓',
    device_no: '中-01-01', specification: '10P', last_replacement_date: '', status: 'missing_photo',
    found: [], missing_slots: ['完成'], naming_suggestions: [], near_candidates: [], marked_reshot: false,
  },
]

describe('reconcile filters', () => {
  it('filters by status', () => {
    expect(filterReconcileRows(rows, 'missing_photo', '')).toEqual([rows[1]])
  })

  it('filters by normalized building', () => {
    expect(filterReconcileRows(rows, '', '一門診')).toEqual([rows[0]])
  })

  it('filters by category', () => {
    expect(filterReconcileRows(rows, '', '', 'extinguisher')).toEqual(rows)
    expect(filterReconcileRows(rows, '', '', 'box')).toEqual([])
  })
})
