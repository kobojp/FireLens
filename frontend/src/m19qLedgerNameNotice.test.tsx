import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Read source-contract regression cases in Node Vitest
import { readFileSync } from 'node:fs'
import { AppConfirmDialog } from './AppConfirmDialog'
import { ledgerNameInUse, isLedgerNameConflict } from './ledgerNameNotice'
import { ApiError } from './api'
import type { LedgerRecord } from './types'

const view = readFileSync(new URL('./ReconcileView.tsx', import.meta.url), 'utf8')
const dialog = readFileSync(new URL('./AppConfirmDialog.tsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

const ledgers: LedgerRecord[] = [
  { id: 1, name: '2026/11 1班 滅火器清冊', source_type: 'text',
    imported_at: '2026-11-14', source_sha256: null, source_filename: null, row_count: 15 },
]

describe('M19-Q ledger duplicate name message and acknowledgment', () => {
  it('recognizes saved names with whitespace, normalization and common case folding', () => {
    expect(ledgerNameInUse(' 2026/11 1班 滅火器清冊 ', ledgers)).toBe(true)
    expect(ledgerNameInUse('２０２６／１１ １班 滅火器清冊', ledgers)).toBe(true)
    expect(ledgerNameInUse('2026/11 2班 滅火器清冊', ledgers)).toBe(false)
    expect(ledgerNameInUse('', ledgers)).toBe(false)
    expect(ledgerNameInUse('2026/11 1班 滅火器清冊', [])).toBe(false)
    expect(ledgerNameInUse('2026/11 1班 滅火器清冊',
      [{ name: '2026/11 2班 滅火器清冊' }])).toBe(false)
  })

  it('recognizes the server 409 unique-name conflict but not unrelated failures', () => {
    expect(isLedgerNameConflict(new ApiError(409, '清冊名稱已存在，請換一個名稱'))).toBe(true)
    expect(isLedgerNameConflict(new ApiError(500, '清冊名稱已存在，請換一個名稱'))).toBe(true)
    expect(isLedgerNameConflict(new ApiError(409, '無法更新掃描狀態'))).toBe(false)
    expect(isLedgerNameConflict(new Error('其他錯誤'))).toBe(false)
  })

  it('renders one acknowledgment button, not a second cancel button', () => {
    const html = renderToStaticMarkup(
      <AppConfirmDialog title="清冊名稱已存在" cancelLabel={null} confirmLabel="確認"
        onCancel={() => undefined} onConfirm={() => undefined}>
        <p>名稱已存在，請修改</p>
      </AppConfirmDialog>,
    )
    expect(html).toContain('role="dialog"')
    expect(html).toContain('aria-modal="true"')
    expect(html).toContain('清冊名稱已存在')
    expect(html).toContain('確認</button>')
    expect(html).not.toContain('取消</button>')
    expect(html.match(/<button/g)).toHaveLength(2) // Close X and Confirm
    expect(dialog).toContain('data-dialog-cancel={!hasCancel || undefined}')
    expect(readFileSync(new URL('./AppDialog.tsx', import.meta.url), 'utf8')).toContain("event.key === 'Escape'")
    expect(css).toContain(':first-child:not(.primary-button)')
  })

  it('retains two buttons and safer cancellation for update confirmations', () => {
    const html = renderToStaticMarkup(
      <AppConfirmDialog title="準備安裝更新" confirmLabel="立即安裝"
        onCancel={() => undefined} onConfirm={() => undefined}>
        <p>已確認簽章</p>
      </AppConfirmDialog>,
    )
    expect(html).toContain('取消</button>')
    expect(html).toContain('立即安裝</button>')
    expect(html.match(/<button/g)).toHaveLength(3)
  })

  it('removes the stale inline duplicate banner and shows dialog only after user action', () => {
    expect(view).not.toContain('ledgerNameUsed && <p className="error-banner"')
    expect(view).toContain('onBlur={() => { if (nameWasEdited && ledgerNameUsed')
    expect(view).toContain('if (ledgerNameUsed) { showDuplicateNameNotice(); return }')
    expect(view).toContain('cancelLabel={null} confirmLabel="確認"')
    expect(view).toContain('setDuplicateNameNotice(null)')
    const closeHandler = view.slice(view.indexOf('function closeDuplicateNameNotice()'), view.indexOf('function changePasteRows('))
    expect(closeHandler).toContain('setNameWasEdited(false)')
    expect(view).toContain('setTextName(event.target.value)')
    expect(view).toContain('window.setTimeout(() => ledgerNameRef.current?.focus(), 0)')
    expect(view).toContain('if (isLedgerNameConflict(err)) showDuplicateNameNotice()')
  })

  it('separates saved name from new-draft name after successful import without clearing sheet data', () => {
    const saved = view.indexOf('? await api.importTextLedger(name, textLedger)')
    const clear = view.indexOf("setTextName('')", saved)
    const reload = view.indexOf('await refreshLedgers(created.id)', saved)
    expect(saved).toBeGreaterThan(0)
    expect(clear).toBeGreaterThan(saved)
    expect(reload).toBeGreaterThan(clear)
    expect(view).toContain('setImportMessage(`已儲存清冊「${name}」；以下可查看核對結果。`)')
    expect(view).toContain('onChanged={async (preferredId) => { clearStaleResults(); await refreshLedgers(preferredId); setError')
    expect(view).not.toContain('setPasteRows(blankLedgerRows())\n      setTextName')
  })
})
