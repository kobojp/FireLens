// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api'
import type { DuplicateReadiness } from './types'

const control = vi.hoisted(() => ({ automatic: false, connected: true, scan: 'idle', pending: 12, duplicate: 'idle', lastScan: null as string | null }))
vi.mock('./api', () => ({ api: {
  listRoots: vi.fn(async () => [{ id: 1, label: '甲照片' }, { id: 2, label: '乙照片' }]),
  issueLabels: vi.fn(async () => []), categories: vi.fn(async () => []), tree: vi.fn(async () => []),
  settings: vi.fn(async () => ({ auto_scan_on_start: control.automatic, auto_scan_min_interval_minutes: 5,
    quick_create: { category_code: 'extinguisher', year: '2026年', period: '', building: '' },
    new_item_panel_collapsed: true, slot_order: {}, theme: 'system' })),
  appInfo: vi.fn(async () => { throw new Error('no app info') }),
  rootStatus: vi.fn(async (id: number) => ({ root_id: id, connected: control.connected, pending_imports: 0, last_scan_at: control.lastScan })),
  offlineQueue: vi.fn(async () => []),
  scanStatus: vi.fn(async (id: number) => ({ root_id: id, state: control.scan, summary: control.scan === 'completed' ? {
    root_id: id, photos: 12, items: 4, categories: {}, added_items: 0, updated_items: 0, removed_items: 0,
    added_photos: 0, updated_photos: 0, removed_photos: 0,
  } : null })),
  startScan: vi.fn(async (id: number) => { control.scan = 'running'; return { root_id: id, state: 'running' } }),
  duplicateReadiness: vi.fn(async (id: number) => ({ root_id: id, total: 12, pending: control.pending,
    cloud_placeholder: 0, duplicate_scan_state: control.duplicate })),
  duplicateScan: vi.fn(),
} }))
vi.mock('./PhotoQualityView', () => ({ PhotoQualityView: (props: {
  guidedRootId: number; guideTicket: number; guideHasPendingPaste: boolean; onGuideFinish: () => void; onGuideCancel: () => void
}) => <section aria-label="測試掃描工作頁" data-root={props.guidedRootId} data-ticket={props.guideTicket}
  data-paste={String(props.guideHasPendingPaste)}>
  <button onClick={props.onGuideFinish}>掃描完成返回</button><button onClick={props.onGuideCancel}>取消掃描引導</button>
</section> }))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
const dialog = () => document.querySelector('[role="dialog"]')
async function render() { await act(async () => root.render(<App />)) }
async function click(text: string) {
  const button = [...document.querySelectorAll('button')].find(node => node.textContent?.includes(text))!
  expect(button).toBeTruthy(); await act(async () => button.click())
}
async function chooseRoot(id: number) {
  const select = container.querySelector('select')!
  await act(async () => { select.value = String(id); select.dispatchEvent(new Event('change', { bubbles: true })) })
}
async function advance() { await act(async () => vi.advanceTimersByTime(300)) }
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks()
  Object.assign(control, { automatic: false, connected: true, scan: 'idle', pending: 12, duplicate: 'idle', lastScan: null })
  container = document.createElement('div'); container.id = 'root'; document.body.append(container); root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount()); vi.clearAllTimers(); vi.useRealTimers(); document.body.replaceChildren()
})

it('offers preparation before any paste, guides the correct root, and never starts duplicate scanning', async () => {
  await render()
  expect(dialog()?.textContent).toContain('甲照片')
  expect(dialog()?.textContent).toContain('12')
  await click('前往重複掃描')
  const page = document.querySelector('[aria-label="測試掃描工作頁"]')!
  expect(page.getAttribute('data-root')).toBe('1')
  expect(page.getAttribute('data-ticket')).toBe('1')
  expect(page.getAttribute('data-paste')).toBe('false')
  expect(api.duplicateScan).not.toHaveBeenCalled()
  await click('掃描完成返回')
  expect(container.querySelector('.success-banner')?.textContent).toContain('可以開始貼上照片')
  expect(dialog()).toBeNull()
})

it('waits until the startup index scan completes', async () => {
  control.automatic = true
  await render()
  expect(api.startScan).toHaveBeenCalledOnce()
  expect(api.duplicateReadiness).not.toHaveBeenCalled()
  control.scan = 'completed'; await advance()
  expect(api.duplicateReadiness).toHaveBeenCalledWith(1)
  expect(dialog()?.textContent).toContain('先完成重複照片掃描')
})

it('checks cached completeness when the automatic scan interval has not elapsed', async () => {
  control.automatic = true; control.lastScan = new Date().toISOString()
  await render()
  expect(api.startScan).not.toHaveBeenCalled()
  expect(dialog()).not.toBeNull()
})

it('keeps a manual rescan from repeating an already dismissed reminder', async () => {
  await render(); await click('稍後再說'); await click('重新掃描')
  control.scan = 'completed'; await advance()
  expect(dialog()).toBeNull(); expect(api.duplicateReadiness).toHaveBeenCalledOnce()
})

it.each(['cancelled', 'error'])('does not prompt after index scan %s', async state => {
  control.automatic = true; await render(); control.scan = state; await advance()
  expect(api.duplicateReadiness).not.toHaveBeenCalled(); expect(dialog()).toBeNull()
})

it.each(['offline', 'complete', 'duplicate-running'])('does not prompt for %s', async state => {
  if (state === 'offline') control.connected = false
  if (state === 'complete') control.pending = 0
  if (state === 'duplicate-running') control.duplicate = 'running'
  await render(); expect(dialog()).toBeNull(); expect(api.duplicateScan).not.toHaveBeenCalled()
})

it('does not repeatedly prompt a dismissed root during the same session', async () => {
  await render(); await click('稍後再說'); await chooseRoot(2)
  expect(dialog()?.textContent).toContain('乙照片')
  await click('稍後再說'); await chooseRoot(1)
  expect(dialog()).toBeNull()
  expect(api.duplicateReadiness).toHaveBeenCalledTimes(2)
})

it('ignores a late response from the previous root', async () => {
  let finish!: (value: DuplicateReadiness) => void
  vi.mocked(api.duplicateReadiness).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  await render(); await chooseRoot(2)
  await act(async () => finish({ root_id: 1, total: 90, pending: 90, cloud_placeholder: 0, duplicate_scan_state: 'idle' }))
  expect(dialog()?.textContent).toContain('乙照片')
  expect(dialog()?.textContent).not.toContain('90')
})

it('keeps a failed advisory request from blocking photo browsing', async () => {
  vi.mocked(api.duplicateReadiness).mockRejectedValueOnce(new Error('offline during check'))
  await render(); expect(dialog()).toBeNull()
  expect(container.querySelector('[aria-label="照片槽位牆"]')).not.toBeNull()
})

it('defers the advisory while the user is on another work page', async () => {
  let finish!: (value: DuplicateReadiness) => void
  vi.mocked(api.duplicateReadiness).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  await render(); await click('照片品質檢查')
  await act(async () => finish({ root_id: 1, total: 12, pending: 12, cloud_placeholder: 0, duplicate_scan_state: 'idle' }))
  expect(dialog()).toBeNull()
  await click('照片瀏覽'); expect(dialog()).not.toBeNull()
})
