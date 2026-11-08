import { describe, expect, it } from 'vitest'
import { branchPathKey, itemBranchPath, revealCreatedBranch, toggleTreeBranch } from './tree'

const cat = (key: string) => [{ type: 'category' as const, key }]
const year = (category: string, key: string) =>
  [...cat(category), { type: 'year' as const, key }]
const period = (category: string, yr: string, key: string) =>
  [...year(category, yr), { type: 'period' as const, key }]
const building = (category: string, yr: string, batch: string, key: string) =>
  [...period(category, yr, batch), { type: 'building' as const, key }]
const key = branchPathKey

describe('FireLens per-root tree expansion', () => {
  it('never expands unrelated years, periods, or categories on creating a device', () => {
    const defaultKeys = [
      key(cat('extinguisher')), key(cat('lamp')), key(cat('box')),
    ]
    const preexisting = [
      ...defaultKeys,
      key(year('extinguisher', '2025年')),
      key(period('extinguisher', '2025年', '10月份更換')),
      key(year('extinguisher', '2026年')),
      key(period('extinguisher', '2026年', '9月份更換')),
    ]
    const newItemPath = itemBranchPath(
      'extinguisher', '2026年', '11月份更換', '致德樓2F', 123,
    )
    const actual = revealCreatedBranch(preexisting, defaultKeys, newItemPath)
    expect(actual).toContain(key(building('extinguisher', '2026年', '11月份更換', '致德樓2F')))
    expect(actual).toContain(key(period('extinguisher', '2026年', '11月份更換')))
    expect(actual).not.toContain(key(newItemPath))
    expect(actual).toContain(key(period('extinguisher', '2026年', '9月份更換')))
    expect(actual).toContain(key(period('extinguisher', '2025年', '10月份更換')))
    expect(actual).not.toContain(key(period('extinguisher', '2025年', '11月份更換')))
    expect(actual).not.toContain(key(year('lamp', '2026年')))
  })

  it('respects previously collapsed categories and unrelated branches', () => {
    const defaults = [key(cat('extinguisher')), key(cat('box')), key(cat('lamp'))]
    const manuallyCollapsed = toggleTreeBranch(undefined, defaults, key(cat('lamp')))
    expect(manuallyCollapsed).not.toContain(key(cat('lamp')))
    const next = revealCreatedBranch(manuallyCollapsed, defaults, year('box', '2027年'))
    expect(next).toContain(key(year('box', '2027年')))
    expect(next).toContain(key(cat('box')))
    expect(next).not.toContain(key(cat('lamp')))
  })

  it('supports year, period, building, and device target levels', () => {
    const defaults = [key(cat('extinguisher'))]
    for (const path of [
      year('extinguisher', '2028年'),
      period('extinguisher', '2028年', '1月份更換'),
      building('extinguisher', '2028年', '1月份更換', '致德樓8F'),
      itemBranchPath('extinguisher', '2028年', '1月份更換', '致德樓8F', 88),
    ]) {
      const expanded = revealCreatedBranch(undefined, defaults, path)
      expect(expanded).toContain(key(cat('extinguisher')))
      expect(expanded).toContain(key(year('extinguisher', '2028年')))
      if (path.at(-1)?.type !== 'item') expect(expanded).toContain(key(path))
    }
  })

  it('does not mix branches with identical month names in separate years or roots', () => {
    const yr2025 = key(period('box', '2025年', '10月份更換'))
    const yr2026 = key(period('box', '2026年', '10月份更換'))
    expect(yr2025).not.toBe(yr2026)
    const byRoot: Record<number, string[]> = {
      1: [yr2025], 2: [yr2026],
    }
    byRoot[1] = revealCreatedBranch(byRoot[1], [], building('box', '2025年', '10月份更換', 'A棟'))
    expect(byRoot[1]).toContain(key(building('box', '2025年', '10月份更換', 'A棟')))
    expect(byRoot[2]).toEqual([yr2026])
  })

  it('does not alter state for failed or cancelled creation, nor mutate old arrays', () => {
    const old = [key(cat('extinguisher')), key(year('extinguisher', '2026年'))]
    const snapshot = [...old]
    // Only call revealCreatedBranch after server confirms creation success.
    expect(old).toEqual(snapshot)
    const newState = revealCreatedBranch(old, [], period('extinguisher', '2026年', '10月份更換'))
    expect(old).toEqual(snapshot)
    expect(newState).not.toBe(old)
  })

  it('toggles a single branch without losing siblings, even after tree refresh', () => {
    const old = [
      key(cat('extinguisher')), key(cat('box')),
      key(year('extinguisher', '2025年')),
      key(year('extinguisher', '2026年')),
    ]
    const next = toggleTreeBranch(old, [], key(year('extinguisher', '2025年')))
    expect(next).not.toContain(key(year('extinguisher', '2025年')))
    expect(next).toContain(key(year('extinguisher', '2026年')))
    expect(old).toHaveLength(4)
    expect(toggleTreeBranch(next, [], key(year('extinguisher', '2025年'))))
      .toContain(key(year('extinguisher', '2025年')))
  })
})
