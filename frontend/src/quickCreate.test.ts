import { describe, expect, it } from 'vitest'
import { normalizeQuickCreate, quickCreateOptions } from './quickCreate'
import type { TreeNode } from './types'

const tree: TreeNode[] = [
  {
    type: 'category', key: 'extinguisher', label: '滅火器', children: [
      {
        type: 'year', key: '2025年', label: '2025年', children: [
          {
            type: 'period', key: '12月份更換', label: '12月份更換', children: [
              { type: 'building', key: '舊棟', label: '舊棟', children: [] },
            ],
          },
        ],
      },
      {
        type: 'year', key: '2026年', label: '2026年', children: [
          {
            type: 'period', key: '9月份更換', label: '9月份更換', children: [
              { type: 'building', key: '中正樓', label: '中正樓', children: [] },
            ],
          },
          {
            type: 'period', key: '10月份更換', label: '10月份更換', children: [
              { type: 'building', key: '中正樓', label: '中正樓', children: [] },
              { type: 'building', key: '致德樓', label: '致德樓', children: [] },
            ],
          },
        ],
      },
    ],
  },
]

describe('quick create helpers', () => {
  it('reads year, period and building choices from the scanned tree', () => {
    const options = quickCreateOptions(tree, {
      category_code: 'extinguisher', year: '2026年', period: '10月份更換', building: '中正樓',
    })
    expect(options.years).toEqual(['2025年', '2026年'])
    expect(options.periods).toEqual(['9月份更換', '10月份更換'])
    expect(options.buildings).toEqual(['中正樓', '致德樓'])
  })

  it('prefers the current calendar year/month when no saved choice exists', () => {
    expect(normalizeQuickCreate(tree, {
      category_code: 'extinguisher', year: '', period: '', building: '',
    }, new Date('2026-10-06T12:00:00'))).toEqual({
      category_code: 'extinguisher', year: '2026年', period: '10月份更換', building: '中正樓',
    })
  })

  it('still exposes periods when an old saved year value does not exactly match the tree key', () => {
    const options = quickCreateOptions(tree, {
      category_code: 'extinguisher', year: '2026', period: '', building: '',
    }, new Date('2026-10-06T12:00:00'))
    expect(options.years).toContain('2026年')
    expect(options.periods).toEqual(['9月份更換', '10月份更換'])
  })

  it('trims stale saved values before matching the scanned tree', () => {
    expect(normalizeQuickCreate(tree, {
      category_code: ' extinguisher ', year: ' 2026年 ', period: ' 10月份更換 ', building: ' 中正樓 ',
    }, new Date('2026-10-06T12:00:00'))).toEqual({
      category_code: 'extinguisher', year: '2026年', period: '10月份更換', building: '中正樓',
    })
  })

  it('keeps an explicit 9月份 selection even when the current calendar month is 10月', () => {
    expect(normalizeQuickCreate(tree, {
      category_code: 'extinguisher', year: '2026年', period: '9月份更換', building: '中正樓',
    }, new Date('2026-10-06T12:00:00')).period).toBe('9月份更換')
  })

  it('keeps a saved building when it still exists in the selected month', () => {
    expect(normalizeQuickCreate(tree, {
      category_code: 'extinguisher', year: '2026年', period: '10月份更換', building: '致德樓',
    }, new Date('2026-10-06T12:00:00')).building).toBe('致德樓')
  })
})
