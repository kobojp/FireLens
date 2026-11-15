import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Source guard assertions for browser-only interaction in Node Vitest
import { readFileSync } from 'node:fs'
import { LedgerManager } from './LedgerManager'
import { ReconcileView } from './ReconcileView'
import { DuplicatePhotoPanel } from './DuplicatePhotoPanel'
import { createReconcileRequestGuard } from './reconcileScope'
import type { LedgerRecord } from './types'

const view = readFileSync(new URL('./ReconcileView.tsx', import.meta.url), 'utf8')
const duplicate = readFileSync(new URL('./DuplicatePhotoPanel.tsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

const ledgers: LedgerRecord[] = [
  { id: 11, name: '第一份清冊', source_type: 'text', row_count: 2,
    imported_at: '2026-11-14', source_filename: null, source_sha256: null },
  { id: 22, name: '第二份清冊', source_type: 'text', row_count: 80,
    imported_at: '2026-11-14', source_filename: null, source_sha256: null },
]

describe('M19-G manual ledger reconciliation and UI workflow', () => {
  it('never opens tutorial automatically, but keeps manual access', () => {
    const html = renderToStaticMarkup(<ReconcileView roots={[]} defaultRootId={null} />)
    expect(html).toContain('查看範例／使用教學')
    expect(html).not.toContain('清冊核對快速教學')
    expect(view).toContain('useState(false)')
    expect(view).not.toContain('localStorage.getItem(TUTORIAL_KEY)')
    expect(view).not.toContain('下次不再自動顯示')
  })

  it('shows a per-row start action before Open, Rename and Delete', () => {
    const html = renderToStaticMarkup(<LedgerManager ledgers={ledgers} selectedId={11}
      onSelect={() => undefined} onReconcile={() => undefined}
      onChanged={async () => undefined} onError={() => undefined} />)
    expect(html.match(/開始核對/g)).toHaveLength(2)
    const second = html.indexOf('第二份清冊')
    expect(second).toBeGreaterThan(0)
    const actions = html.slice(second, second + 1000)
    expect(actions.indexOf('開始核對')).toBeLessThan(actions.indexOf('開啟'))
    expect(actions.indexOf('開啟')).toBeLessThan(actions.indexOf('重新命名'))
    expect(actions.indexOf('重新命名')).toBeLessThan(actions.indexOf('刪除'))
  })

  it('disables row edits during active reconciliation, and does not offer a shortcut without callback', () => {
    const html = renderToStaticMarkup(<LedgerManager ledgers={ledgers} selectedId={11}
      onSelect={() => undefined} onReconcile={() => undefined}
      reconcilingLedgerId={22} reconcileDisabled
      onChanged={async () => undefined} onError={() => undefined} />)
    expect(html).toContain('核對中…')
    expect(html).toContain('disabled=""')
    const plain = renderToStaticMarkup(<LedgerManager ledgers={ledgers} selectedId={11}
      onSelect={() => undefined} onChanged={async () => undefined} onError={() => undefined} />)
    expect(plain).not.toContain('開始核對')
  })

  it('passes clicked ledger ID to API, invalidates old results, and scrolls after result commit', () => {
    expect(view).toContain('onReconcile={(id) => { void runReconcile(id) }}')
    expect(view).toContain('api.reconcile(rootId, clickedLedgerId, period || undefined, categoryCode)')
    expect(view).toContain('setLedgerId(clickedLedgerId)')
    expect(view).toContain('reconcileBusyVersion.current !== null')
    expect(view).toContain('!ledgers.some(row => row.id === clickedLedgerId)')
    expect(view).toContain('scrollResult.current = next')
    expect(view).toContain('scrollResult.current !== result')
    expect(view).toContain('resultTarget.current')
    expect(view).toContain('scrollIntoView(')
    expect(view).toContain('prefers-reduced-motion: reduce')
    expect(view).toContain('reconcile-result-target')
    expect(css).toContain('.reconcile-result-target { scroll-margin-top:')
  })

  it('rejects stale responses and cancelled work using the generation guard', () => {
    const requests = createReconcileRequestGuard()
    const first = requests.next()
    const later = requests.next()
    expect(requests.isCurrent(first)).toBe(false)
    expect(requests.isCurrent(later)).toBe(true)
    requests.invalidate()
    expect(requests.isCurrent(later)).toBe(false)
  })

  it('styles scan, cancel and refresh like exports without breaking guidance spotlight', () => {
    const html = renderToStaticMarkup(<DuplicatePhotoPanel rootId={null} roots={[]}
      onOpenItem={() => undefined} guideTicket={4} />)
    expect(html).toContain('quality-action-scan scan-guide-target')
    expect(html).toContain('quality-action-cancel')
    expect(html).toContain('quality-action-refresh')
    expect(html).toContain('quality-action-csv')
    expect(html).toContain('quality-action-excel')
    expect(duplicate).toContain('manualRefreshBusy.current')
    expect(duplicate).toContain('disabled={refreshing || rootId === null}')
    expect(duplicate).toContain("job?.state === 'running' ? '掃描中…'")
    expect(css).toContain('.quality-action-scan')
    expect(css).toContain('.quality-action:disabled')
  })
})
