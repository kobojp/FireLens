import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Node-only project source assertions
import { readFileSync } from 'node:fs'
import { blankLedgerRows, filledLedgerCount, MAX_LEDGER_PASTE_ROWS, parseLedgerPaste,
  pasteLedgerCells, serializeLedgerRows, LedgerPasteSheet } from './LedgerPasteSheet'
import { LedgerManager } from './LedgerManager'
import type { LedgerRecord } from './types'

const view = readFileSync(new URL('./ReconcileView.tsx', import.meta.url), 'utf8')
const manager = readFileSync(new URL('./LedgerManager.tsx', import.meta.url), 'utf8')
const settings = readFileSync(new URL('./SettingsView.tsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('./LedgerPasteSheet.css', import.meta.url), 'utf8')
const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')

describe('M19-L Excel/Google Sheets ledger paste workspace', () => {
  it('parses two-column TSV, Windows CRLF and quoted escaped cells', () => {
    expect(parseLedgerPaste('致德樓8F\t致-08-19\r\n中正樓B2F\t中-B2-05\r\n')).toEqual([
      ['致德樓8F', '致-08-19'], ['中正樓B2F','中-B2-05'],
    ])
    expect(parseLedgerPaste('"第一,二樓"\t"動-01-15"\n')).toEqual([['第一,二樓', '動-01-15']])
    expect(parseLedgerPaste('"兩""段"\t"中-02-03"')).toEqual([['兩"段','中-02-03']])
    expect(() => parseLedgerPaste('"未關閉')).toThrow('引號')
  })

  it('pastes two columns at A1, skips headers, and preserves existing rows', () => {
    const initial = blankLedgerRows()
    const updated = pasteLedgerCells(initial,
      '棟別樓層\t設備編號\n致德樓8F\t致-08-19\n中正樓B2F\t中-B2-05', 0, 0)
    expect(updated[0]).toEqual({ section:'致德樓8F', device:'致-08-19' })
    expect(updated[1]).toEqual({ section:'中正樓B2F', device:'中-B2-05' })
    expect(initial[0]).toEqual({ section:'', device:'' })
    expect(filledLedgerCount(updated)).toBe(2)
  })

  it('maps a one-column list onto equipment numbers even from A1', () => {
    const updated = pasteLedgerCells(blankLedgerRows(), '動-01-15\n動-03-08')
    expect(updated[0]).toEqual({ section:'', device:'動-01-15' })
    expect(updated[1]).toEqual({ section:'', device:'動-03-08' })
    expect(pasteLedgerCells(blankLedgerRows(), '設備編號\n動-01-15')[0].device).toBe('動-01-15')
    expect(pasteLedgerCells(blankLedgerRows(), '致-08-19', 2, 1)[2].device).toBe('致-08-19')
  })

  it('serializes to the existing FireLens server parser semantics', () => {
    const rows = [{ section:'', device:'動-01-15' }, { section:'致德樓8F', device:'致-08-19' },
      { section:'', device:'' }]
    expect(serializeLedgerRows(rows)).toBe('動-01-15\n致德樓8F\t致-08-19')
  })

  it('rejects extra columns, over-limit and malformed clipboard content', () => {
    expect(() => pasteLedgerCells(blankLedgerRows(), 'A\tB\tC')).toThrow('兩欄')
    expect(() => pasteLedgerCells(blankLedgerRows(), 'A\tB', 2, 1)).toThrow('兩欄')
    expect(() => pasteLedgerCells(blankLedgerRows(), '動-01-01', MAX_LEDGER_PASTE_ROWS, 0))
      .toThrow('10,000')
  })

  it('renders full-size editable spreadsheet with row numbers and keyboard handler', () => {
    const html = renderToStaticMarkup(<LedgerPasteSheet rows={blankLedgerRows()}
      onChange={() => undefined} onUndo={() => undefined} onError={() => undefined} />)
    expect(html).toContain('貼上清冊試算表')
    expect(html).toContain('Ａ　棟別樓層')
    expect(html).toContain('Ｂ　設備編號')
    expect(html).toContain('第 1 列')
    expect(html).toContain('data-cell="0,0"')
    expect(html).toContain('data-cell="0,1"')
    expect(css).toContain('max-height: min(520px, 62vh)')
  })

  it('uses a separate full-width card and invalidates stale text preview', () => {
    expect(view).toContain('className="panel-card ledger-paste-card"')
    expect(view).toContain('className="reconcile-import-grid ledger-sources-grid"')
    expect(view).toContain('if (pendingImport?.kind === \'text\') setPendingImport(null)')
    expect(view).toContain('await api.previewTextLedger')
    expect(view).toContain('await api.importTextLedger')
    expect(view).toContain('ledgerNameUsed')
    expect(app).toContain('settings={appSettings}')
  })

  it('does not accidentally split an embedded new line into another equipment row', () => {
    const filled = pasteLedgerCells(blankLedgerRows(), '"致德樓\n8F"\t致-08-19')
    expect(filled[0]).toEqual({ section: '致德樓 8F', device: '致-08-19' })
    expect(serializeLedgerRows(filled)).toBe('致德樓 8F\t致-08-19')
  })

  it('server-renders only 5 of 12 ledgers by default and can collapse their list', () => {
    const ledgers: LedgerRecord[] = Array.from({ length: 12 }, (_, index) => ({
      id: index + 1, name: `清冊 ${index + 1}`, source_type: 'text',
      imported_at: '2026-11-14', source_sha256: null, source_filename: null, row_count: 2,
    }))
    const expanded = renderToStaticMarkup(
      <LedgerManager ledgers={ledgers} selectedId={null} onSelect={() => undefined}
        onChanged={async () => undefined} onError={() => undefined} pageSize={5} />,
    )
    expect(expanded).toContain('清冊 1</b>')
    expect(expanded).toContain('清冊 5</b>')
    expect(expanded).not.toContain('清冊 6</b>')
    expect(expanded).toContain('第 1／3 頁')
    const collapsed = renderToStaticMarkup(
      <LedgerManager ledgers={ledgers} selectedId={null} defaultCollapsed
        onSelect={() => undefined} onChanged={async () => undefined}
        onError={() => undefined} pageSize={5} />,
    )
    expect(collapsed).toContain('清冊清單已收合')
    expect(collapsed).not.toContain('清冊 1</b>')
  })

  it('keeps saved ledgers paginated and collapsible, with persisted settings fields', () => {
    expect(manager).toContain('visibleLedgers.map')
    expect(manager).toContain('pageSize = 5')
    expect(manager).toContain('aria-expanded={!collapsed}')
    expect(manager).toContain('清冊管理分頁')
    expect(manager).toContain('第 {currentPage + 1}／{pageCount} 頁')
    expect(settings).toContain('清冊管理清單預設收合')
    expect(settings).toContain('每頁顯示筆數')
    expect(view).toContain('defaultCollapsed={settings?.ledger_list_collapsed ?? false}')
    expect(view).toContain('pageSize={settings?.ledger_page_size ?? 5}')
  })
})
