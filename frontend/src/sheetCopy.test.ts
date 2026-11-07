import { describe, expect, it } from 'vitest'
import {
  boundsFor, boundsLabel, columnName, inSelection, tsvFromRows, trimTrailingBlankRows,
  loadCopyRows,
} from './sheetCopy'
import type { SheetSelection } from './sheetCopy'

describe('FireLens Google Sheets selection / clipboard', () => {
  const column: SheetSelection = { kind: 'column', column: 2 }
  it('supports columns A through AD and preserves B values', () => {
    expect(columnName(1)).toBe('A')
    expect(columnName(2)).toBe('B')
    expect(columnName(26)).toBe('Z')
    expect(columnName(27)).toBe('AA')
    expect(columnName(30)).toBe('AD')
    expect(boundsLabel(boundsFor(column, 550, false))).toBe('B2:B550')
    expect(boundsLabel(boundsFor(column, 550, true))).toBe('B1:B550')
    expect(inSelection(column, 502, 2)).toBe(true)
    expect(inSelection(column, 502, 3)).toBe(false)
  })

  it('selects ranges with Shift including reversed corners and multiple columns', () => {
    const selection: SheetSelection = {
      kind: 'range', anchorRow: 104, anchorColumn: 5, endRow: 102, endColumn: 2,
    }
    expect(boundsLabel(boundsFor(selection, 2000, false))).toBe('B102:E104')
    expect(inSelection(selection, 103, 3)).toBe(true)
    expect(inSelection(selection, 101, 3)).toBe(false)
    expect(inSelection(selection, 103, 6)).toBe(false)
  })

  it('formats TSV preserving empty equipment ID rows, leading zeros and variant characters', () => {
    const rows = [
      ['致-02-08', '00123'],
      ['', ''],
      ['致徳樓-02-09', '10P'],
      ['內容含\tTab', '行1\n行2'],
      ['"雙引號"', '=SUM(A1:A2)'],
    ]
    const tsv = tsvFromRows(rows)
    expect(tsv.split('\n').length).toBe(6)
    expect(tsv).toContain('致-02-08\t00123\n\t\n致徳樓-02-09\t10P')
    expect(tsv).toContain('"內容含\tTab"')
    expect(tsv).toContain('"行1\n行2"')
    expect(tsv).toContain('"""雙引號"""\t=SUM(A1:A2)')
  })

  it('trims only trailing blanks and keeps middle empty rows for whole-column copy', () => {
    expect(trimTrailingBlankRows([
      ['致-02-08'], [''], ['致-02-12'], [''], [''],
    ])).toEqual([['致-02-08'], [''], ['致-02-12']])
  })

  it('rejects over-limit whole column and excessive multi-cell area without truncation', () => {
    expect(() => boundsFor(column, 20001, false)).toThrow('20,000')
    const area: SheetSelection = {
      kind: 'range', anchorRow: 1, anchorColumn: 1,
      endRow: 10000, endColumn: 30,
    }
    expect(() => boundsFor(area, 10000, true)).toThrow('100,000')
    expect(boundsFor({
      kind: 'range', anchorRow: 1, anchorColumn: 1,
      endRow: 100, endColumn: 2,
    }, 250000, true)).toEqual({
      startRow: 1, endRow: 100, startColumn: 1, endColumn: 2,
    })
  })

  it('fetches across 100/200-row pages, retaining internal blank rows and equipment numbers', async () => {
    const called: string[] = []
    const progress: number[] = []
    const bounds = boundsFor({ kind: 'column', column: 2 }, 403, false)
    const rows = await loadCopyRows(bounds, async (first, last) => {
      called.push(first + ':' + last)
      return Array.from({ length: last - first + 1 }, (_, index) => {
        const row = first + index
        return [row === 2 ? '00123' : row === 202 ? '' : '致-02-' + row]
      })
    }, () => false, (loaded) => progress.push(loaded))
    expect(called).toEqual(['2:201', '202:401', '402:403'])
    expect(progress).toEqual([200, 400, 402])
    expect(rows[0]).toEqual(['00123'])
    expect(rows[200]).toEqual([''])
    expect(rows.at(-1)).toEqual(['致-02-403'])
    expect(rows.length).toBe(402)
  })

  it('fails closed on incomplete Google API response instead of copying partial rows', async () => {
    const bounds = boundsFor({ kind: 'column', column: 2 }, 500, false)
    let calls = 0
    await expect(loadCopyRows(bounds, async (first, last) => {
      calls++
      if (calls === 2) return [['partial']]
      return Array.from({ length: last - first + 1 }, () => ['OK'])
    }, () => false, () => undefined)).rejects.toThrow('不完整')
    expect(calls).toBe(2)
  })

  it('interrupts copy when user leaves the tab or cancels halfway', async () => {
    const bounds = boundsFor({ kind: 'column', column: 1 }, 1000, true)
    let cancelled = false
    let calls = 0
    await expect(loadCopyRows(bounds, async (first, last) => {
      calls++
      cancelled = true
      return Array.from({ length: last - first + 1 }, () => ['X'])
    }, () => cancelled, () => undefined)).rejects.toThrow('已取消')
    expect(calls).toBe(1)
  })

  it('rejects row outside copy ceiling and an empty selection after header exclusion', () => {
    expect(() => boundsFor({
      kind: 'range', anchorRow: 1, anchorColumn: 1,
      endRow: 20001, endColumn: 1,
    }, 250000, true)).toThrow('100,000')
    expect(boundsFor(column, 1, false).endRow).toBe(1)
    expect(boundsFor(column, 1, false).startRow).toBe(2)
  })
})
