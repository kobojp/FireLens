import { describe, expect, it } from 'vitest'
import { previewCanExecute, safeCandidateIds, toggleCandidate } from './organizer'
import type { OrganizerRenameCandidate, RenamePreview } from './types'

const row = (id: string, safe: boolean): OrganizerRenameCandidate => ({
  candidate_id: id,
  photo_id: 1,
  item_id: 1,
  category: 'extinguisher',
  category_name: '滅火器',
  code: '中-01-01',
  building: '中正樓',
  period: '9月份更換',
  source_relative: `a/${id}.JPG`,
  target_relative: `a/${id}.jpg`,
  source_name: `${id}.JPG`,
  target_name: `${id}.jpg`,
  sha256: 'a'.repeat(64),
  reason: '副檔名正規化',
  safe,
  blocked_reason: safe ? null : '目標檔名已存在',
})

describe('organizer helpers', () => {
  it('selects only safe candidates', () => {
    expect(safeCandidateIds([row('a', true), row('b', false)])).toEqual(['a'])
  })

  it('toggles candidate selection', () => {
    expect(toggleCandidate([], 'a')).toEqual(['a'])
    expect(toggleCandidate(['a', 'b'], 'a')).toEqual(['b'])
  })

  it('requires a clean explicit preview before execution', () => {
    expect(previewCanExecute(null)).toBe(false)
    const base: RenamePreview = {
      root_id: 1,
      selected: [row('a', true)],
      missing_candidate_ids: [],
      safe_count: 1,
      blocked_count: 0,
    }
    expect(previewCanExecute(base)).toBe(true)
    expect(previewCanExecute({ ...base, blocked_count: 1 })).toBe(false)
    expect(previewCanExecute({ ...base, missing_candidate_ids: ['stale'] })).toBe(false)
  })
})
