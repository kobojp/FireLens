import { describe, expect, it } from 'vitest'
import { qualityProgress } from './qualityProgress'
import type { QualityJob } from './types'

const running: QualityJob = {
  state: 'running', phase: 'analyzing', done: 50, total: 100,
  analyzed: 50, cached: 0, skipped: 0, flagged: 0,
  cancel: false, error: '', started_at: 100, analysis_started_at: 105,
}

describe('M18-H scan ETA', () => {
  it('estimates from observed analysis throughput, not arbitrary percentage', () => {
    expect(qualityProgress(running, 115)).toEqual({
      percent: 50, remaining: '約 10 秒', phase: '正在分析圖片品質',
    })
  })
  it('handles indexing, unknown size, and small samples without invented ETA', () => {
    expect(qualityProgress({ ...running, phase: 'indexing', total: 0, done: 0 }, 200).percent).toBeNull()
    expect(qualityProgress({ ...running, phase: 'indexing', total: 0, done: 0 }, 200).remaining).toBe('計算中…')
    expect(qualityProgress({ ...running, done: 0 }, 115).remaining).toBe('計算中…')
    expect(qualityProgress({ ...running, done: 4 }, 115).remaining).toBe('計算中…')
    expect(qualityProgress({ ...running, analysis_started_at: null }, 115).remaining).toBe('計算中…')
  })
  it('never counts down after cancellation, errors or completion', () => {
    for (const state of ['completed', 'cancelled', 'error']) {
      expect(qualityProgress({ ...running, state }, 500).remaining).toBe('—')
    }
    expect(qualityProgress({ ...running, state: 'completed', total: 0, done: 0 }, 500).percent).toBe(100)
    expect(qualityProgress({ ...running, total: 100, done: 200 }, 500).percent).toBe(100)
  })
})
