import { describe, expect, it } from 'vitest'
import { countByStatus, countItems } from './tree'
import type { TreeNode } from './types'

const sample: TreeNode[] = [
  {
    type: 'category',
    key: 'extinguisher',
    label: '滅火器',
    children: [
      {
        type: 'year',
        key: '2026年',
        label: '2026年',
        children: [
          { type: 'item', key: '1', id: 1, label: '中-01-01', status: 'complete' },
          { type: 'item', key: '2', id: 2, label: '中-01-02', status: 'empty' },
        ],
      },
    ],
  },
]

describe('tree helpers', () => {
  it('counts item nodes', () => {
    expect(countItems(sample)).toBe(2)
  })

  it('counts item status', () => {
    expect(countByStatus(sample)).toEqual({ complete: 1, empty: 1 })
  })
})
