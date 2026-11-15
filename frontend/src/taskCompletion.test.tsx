// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppDialogHost, confirmDialog, ModalBackdrop } from './AppDialog'
import { InspectorImageViewer } from './InspectorImageViewer'
import { photosInDisplayOrder } from './slots'
import { ReconcileView } from './ReconcileView'
import { DuplicatePhotoPanel } from './DuplicatePhotoPanel'
import { StatisticsView } from './StatisticsView'
import { RetainedView } from './RetainedView'
import { api } from './api'
import { LedgerManager } from './LedgerManager'
import { SyncResultPanel } from './SyncResultPanel'
import { RootExclusionSettings } from './RootExclusionSettings'
import type { ItemDetail, ReconcileResult, RootRecord, SharedIssueStatus } from './types'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
let root: Root
let container: HTMLDivElement
const scroll = vi.fn()
const roots = [{ id: 1, label: '合成照片' }] as RootRecord[]
const result = { root_id: 1, ledger_name: '測試清冊', category_code: 'extinguisher',
  total: 1, complete: 1, completion_rate: 100, classification_counts: { complete: 1 },
  rows: [], status_counts: {}, building_progress: [] } as unknown as ReconcileResult

async function render(element: React.ReactNode) { await act(async () => root.render(element)) }
async function click(text: string) {
  const button = [...document.querySelectorAll<HTMLButtonElement>('button')].find(node => !node.closest('[inert]') && !(node.closest('.preview-backdrop') as HTMLElement | null)?.inert && node.textContent?.includes(text))
  expect(button, text).toBeTruthy()
  await act(async () => button!.click())
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  container = document.createElement('div'); container.id = 'root'; document.body.append(container)
  root = createRoot(container)
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { value: scroll, configurable: true })
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
  scroll.mockClear()
})
afterEach(async () => {
  await act(async () => root.unmount())
  document.body.replaceChildren()
  vi.restoreAllMocks(); vi.unstubAllGlobals()
})

describe('M19-G dialogs and equipment-local photo viewing', () => {
  it('waits for explicit approval, defaults to cancel, prevents re-entry and restores focus', async () => {
    await render(<><button>原操作</button><AppDialogHost /></>)
    const trigger = container.querySelector('button')!; trigger.focus()
    const write = vi.fn()
    let pending!: Promise<void>
    await act(async () => { pending = confirmDialog('刪除合成照片？').then(ok => { if (ok) write() }) })
    expect(write).not.toHaveBeenCalled()
    expect(document.activeElement?.textContent).toBe('取消')
    expect(container.inert).toBe(true)
    expect(await confirmDialog('不應堆疊')).toBe(false)
    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    await pending
    expect(write).not.toHaveBeenCalled()
    expect(container.inert).toBe(false)
    expect(document.activeElement).toBe(trigger)
    await act(async () => { pending = confirmDialog('確認後才執行').then(ok => { if (ok) write() }) })
    await click('確認執行'); await pending
    expect(write).toHaveBeenCalledOnce()
  })

  it('traps Tab/Shift+Tab and unlocks background when nested dialogs close', async () => {
    await render(<><ModalBackdrop className="preview-backdrop" onCancel={() => undefined}>
      <section role="dialog"><button>取消</button><button>儲存</button></section>
    </ModalBackdrop><AppDialogHost /></>)
    const buttons = [...document.querySelectorAll<HTMLButtonElement>('.preview-backdrop button')]
    buttons[1].focus()
    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })))
    expect(document.activeElement).toBe(buttons[0])
    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true })))
    expect(document.activeElement).toBe(buttons[1])
    let pending!: Promise<boolean>
    await act(async () => { pending = confirmDialog('第二層') })
    await click('取消'); expect(await pending).toBe(false)
    expect(container.inert).toBe(true)
    expect(document.body.style.overflow).toBe('hidden')
    await render(<span>全部關閉</span>)
    expect(container.inert).toBe(false)
    expect(document.body.style.overflow).toBe('')
  })

  it('follows displayed slots then unmapped photos, deduplicating without another equipment', () => {
    const item = { photos: [{ id: 4, slot: null }, { id: 2, slot: '中' },
      { id: 1, slot: '前' }, { id: 3, slot: '中' }] } as unknown as ItemDetail
    expect(photosInDisplayOrder(item, ['前', '中', '後', '中']).map(photo => photo.id)).toEqual([1, 2, 3, 4])
  })

  it('respects first/last boundaries and resets zoom and position after arrow navigation', async () => {
    const images = [1, 2, 3].map(id => ({ id, filename: `${id}.jpg`, title: 'LB-02-03', subtitle: '前中後', path: `${id}.jpg`, src: `/${id}` }))
    const select = vi.fn()
    await render(<InspectorImageViewer images={images} activeId={1} onSelect={select} onClose={() => undefined} />)
    expect(document.querySelector<HTMLButtonElement>('[aria-label="上一張照片"]')!.disabled).toBe(true)
    await act(async () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' })))
    expect(select).not.toHaveBeenCalled()
    await act(async () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' })))
    expect(select).toHaveBeenLastCalledWith(2)
    const canvas = document.querySelector<HTMLDivElement>('.inspector-lightbox-canvas')!
    canvas.scrollTop = 200; canvas.scrollLeft = 300
    await render(<InspectorImageViewer images={images} activeId={3} onSelect={select} onClose={() => undefined} />)
    expect(document.querySelector<HTMLButtonElement>('[aria-label="下一張照片"]')!.disabled).toBe(true)
    expect(canvas.scrollTop).toBe(0); expect(canvas.scrollLeft).toBe(0)
    expect(document.querySelector<HTMLInputElement>('input[type="range"]')!.value).toBe('1')
  })
})

function reconcileMocks() {
  vi.spyOn(api, 'tree').mockResolvedValue([])
  vi.spyOn(api, 'ledgers').mockResolvedValue([{ id: 1, name: '測試清冊' }] as never)
  vi.spyOn(api, 'aliases').mockResolvedValue([])
}

describe('M19-G reconciliation result navigation', () => {
  it('cancels ledger deletion without calling the API', async () => {
    const remove = vi.spyOn(api, 'deleteLedger').mockResolvedValue({} as never)
    await render(<LedgerManager ledgers={[{ id: 1, name: '合成清冊', row_count: 3 }] as never}
      selectedId={1} onSelect={() => undefined} onChanged={async () => undefined} onError={() => undefined} />)
    await click('刪除')
    expect(document.querySelector('[aria-label="確認刪除清冊"]')).not.toBeNull()
    expect(document.activeElement?.textContent).toBe('取消')
    await click('取消')
    expect(remove).not.toHaveBeenCalled()
    expect(document.querySelector('[role="alertdialog"]')).toBeNull()
  })
  it('keeps tutorials closed for both new and previously opted-out installations; manual open works', async () => {
    reconcileMocks()
    for (const value of [null, '0', '1']) {
      await render(<span />)
      localStorage.clear()
      if (value) localStorage.setItem('firelens.reconcile.tutorial.dismissed.v1', value)
      await render(<ReconcileView roots={roots} defaultRootId={1} />)
      expect(document.querySelector('[role="dialog"]')).toBeNull()
      await click('查看範例')
      expect(document.querySelector('[aria-label="清冊使用教學"]')).not.toBeNull()
      await click('我知道了')
    }
  })

  it('scrolls once after a successful user request, but not when filtering or returning', async () => {
    reconcileMocks(); vi.spyOn(api, 'reconcile').mockResolvedValue(result)
    await render(<ReconcileView roots={roots} defaultRootId={1} />)
    expect(scroll).not.toHaveBeenCalled()
    await click('開始核對')
    expect(scroll).toHaveBeenCalledExactlyOnceWith({ block: 'start', behavior: 'smooth' })
    await render(<ReconcileView roots={roots} defaultRootId={1} isActive={false} />)
    await render(<ReconcileView roots={roots} defaultRootId={1} isActive />)
    expect(scroll).toHaveBeenCalledTimes(1)
  })

  it('does not scroll after failure, stale scope responses, or a hidden page finishing', async () => {
    reconcileMocks()
    const request = deferred<ReconcileResult>()
    vi.spyOn(api, 'reconcile').mockReturnValue(request.promise)
    await render(<ReconcileView roots={roots} defaultRootId={1} />)
    await click('開始核對')
    await render(<ReconcileView roots={roots} defaultRootId={1} isActive={false} />)
    await act(async () => request.resolve(result))
    expect(scroll).not.toHaveBeenCalled()
    await render(<ReconcileView roots={roots} defaultRootId={1} isActive />)
    expect(scroll).not.toHaveBeenCalled()
    vi.mocked(api.reconcile).mockRejectedValueOnce(new Error('合成核對失敗'))
    await click('開始核對')
    expect(scroll).not.toHaveBeenCalled()
    expect(container.textContent).toContain('合成核對失敗')
  })

  it('rejects a pending result after another saved ledger is opened', async () => {
    reconcileMocks()
    vi.mocked(api.ledgers).mockResolvedValue([{ id: 1, name: '甲' }, { id: 2, name: '乙' }] as never)
    vi.spyOn(api, 'ledger').mockResolvedValue({ id: 2, name: '乙', rows: [], source_type: 'text' } as never)
    const pending = deferred<ReconcileResult>()
    vi.spyOn(api, 'reconcile').mockReturnValue(pending.promise)
    await render(<ReconcileView roots={roots} defaultRootId={1} />)
    await click('開始核對')
    const buttons = [...container.querySelectorAll<HTMLButtonElement>('.ledger-actions button')].filter(button => button.textContent === '開啟')
    await act(async () => buttons[1].click())
    await act(async () => pending.resolve(result))
    expect(scroll).not.toHaveBeenCalled()
    expect(container.querySelector('.reconcile-result-target')).toBeNull()
  })

  it('locates the result after save-and-reconcile with reduced motion respected', async () => {
    reconcileMocks()
    vi.mocked(window.matchMedia).mockReturnValue({ matches: true } as MediaQueryList)
    vi.spyOn(api, 'previewTextLedger').mockResolvedValue({ rows: [], valid_count: 1, total_rows: 1, duplicate_count: 0, invalid_count: 0 } as never)
    vi.spyOn(api, 'importTextLedger').mockResolvedValue({ id: 1 } as never)
    vi.spyOn(api, 'reconcile').mockResolvedValue(result)
    await render(<ReconcileView roots={roots} defaultRootId={1} />)
    const cell = container.querySelector<HTMLInputElement>('input[aria-label="第 1 列 設備編號"]')!
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(cell, '中-01-001')
      cell.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await click('解析預覽'); await click('儲存並開始核對')
    expect(scroll).toHaveBeenCalledExactlyOnceWith({ block: 'start', behavior: 'auto' })
  })
})

describe('M19-G duplicate toolbar and M19-H session summary', () => {
  it('loads and saves only the selected root exclusions without a global replacement', async () => {
    vi.spyOn(api, 'rootExclusions').mockImplementation(async id => ({ root_id: id, names: id === 1 ? ['水帶'] : ['備份'] }))
    const save = vi.spyOn(api, 'saveRootExclusions').mockImplementation(async (id, names) => ({ root_id: id, names, saved: names, rescan_required: true }))
    const globalSave = vi.spyOn(api, 'saveSettings')
    await render(<RootExclusionSettings roots={[{ id: 1, label: '甲' }, { id: 2, label: '乙' }] as RootRecord[]} />)
    expect(container.textContent).toContain('水帶')
    const select = container.querySelector('select')!
    await act(async () => { select.value = '2'; select.dispatchEvent(new Event('change', { bubbles: true })) })
    expect(container.textContent).toContain('備份')
    expect(container.textContent).not.toContain('水帶')
    await click('移除排除'); await click('儲存此根目錄')
    expect(save).toHaveBeenCalledExactlyOnceWith(2, [])
    expect(globalSave).not.toHaveBeenCalled()
    await act(async () => { select.value = '1'; select.dispatchEvent(new Event('change', { bubbles: true })) })
    expect(container.textContent).toContain('水帶')
  })
  it('shows conflicts separately from applied updates and can filter to conflicts', async () => {
    await render(<SyncResultPanel result={{ root_id: 1, at: '2026-11-14', local_total: 1,
      summary: { added: 1, updated: 0, cleared: 0, conflicts: 1 },
      changes: [{ kind: 'added', path: '燈具/甲', code: '甲', category: 'lamp', category_name: '燈具',
        building: null, before: null, after: '壓力錶故障', device: 'a'.repeat(32), at: '2026-11-14' }],
      conflicts: [{ key: 'issue:lamp:燈具/乙', kind: 'issue', candidates: [
        { event_id: 'b', device: 'b'.repeat(32), at: '2026-11-14', label_name: '瓶身超過10年', value: { code: '乙', path: '燈具/乙' } },
        { event_id: 'c', device: 'c'.repeat(32), at: '2026-11-14', label_name: '清除異常', value: { code: '乙', path: '燈具/乙' } },
      ] }],
    }} />)
    const select = container.querySelector('select')!
    await act(async () => { select.value = 'conflict'; select.dispatchEvent(new Event('change', { bubbles: true })) })
    expect(container.querySelector('tbody')!.textContent).toContain('尚未套用')
    expect(container.querySelector('tbody')!.textContent).toContain('瓶身超過10年 ↔ 清除異常')
    expect(container.querySelector('tbody')!.textContent).not.toContain('壓力錶故障')
    expect(container.querySelector('.sync-summary')!.textContent).toContain('更新 0 筆')
  })

  it('loads affected equipment before restoration confirmation and cancels without restoring', async () => {
    vi.spyOn(api, 'issueStatistics').mockResolvedValue({ labels: [], items: [], total: 0 })
    vi.spyOn(api, 'sharedIssueStatus').mockResolvedValue({ enabled: true, root_id: 1,
      pending: 0, local_total: 1, state: 'local_read', last_read: null, shared_folder: '', warning: '', manual_review: false })
    vi.spyOn(api, 'sharedIssueBackups').mockResolvedValue([{ id: 'backup', time: '2026-11-14', reason: '合成備份', labels: 3, items: 0 }])
    vi.spyOn(api, 'sharedIssueConflicts').mockResolvedValue([])
    const preview = vi.spyOn(api, 'previewSharedIssueBackup').mockResolvedValue({ id: 'backup', time: '2026-11-14', reason: '', labels: 3, items: 0,
      removing: 1, changes: [{ path: '燈具/LB-02-03', before: '壓力錶故障', after: null, kind: 'cleared' }] })
    const restore = vi.spyOn(api, 'restoreSharedIssueBackup').mockResolvedValue({} as never)
    await render(<><StatisticsView roots={roots} onOpenItem={() => undefined} onLabelsChanged={() => undefined} /><AppDialogHost /></>)
    await click('復原本機')
    expect(preview).toHaveBeenCalledExactlyOnceWith(1, 'backup')
    expect(document.querySelector('[role="alertdialog"]')!.textContent).toContain('燈具/LB-02-03：壓力錶故障 → 無異常')
    expect(restore).not.toHaveBeenCalled()
    await click('取消')
    expect(restore).not.toHaveBeenCalled()
  })
  it('requires approval for full duplicate scan and keeps cancel free of side effects', async () => {
    vi.spyOn(api, 'categories').mockResolvedValue([])
    vi.spyOn(api, 'duplicateGallery').mockResolvedValue({ groups: [], total: 0 } as never)
    vi.spyOn(api, 'duplicateScanStatus').mockResolvedValue({ state: 'idle' } as never)
    const start = vi.spyOn(api, 'duplicateScan').mockResolvedValue({ state: 'running', total: 0, done: 0 } as never)
    await render(<><DuplicatePhotoPanel roots={roots} rootId={1} onOpenItem={() => undefined} /><AppDialogHost /></>)
    const select = [...container.querySelectorAll('select')].find(node => node.querySelector('option[value="full"]'))!
    await act(async () => { select.value = 'full'; select.dispatchEvent(new Event('change', { bubbles: true })) })
    await click('開始重複掃描'); await click('取消')
    expect(start).not.toHaveBeenCalled()
    await click('開始重複掃描'); await click('確認執行')
    expect(start).toHaveBeenCalledExactlyOnceWith(1, true)
  })
  it('refreshes only the list, highlights the guide, and blocks scan double clicks while starting', async () => {
    vi.spyOn(api, 'categories').mockResolvedValue([])
    vi.spyOn(api, 'duplicateGallery').mockResolvedValue({ groups: [], total: 0 } as never)
    vi.spyOn(api, 'duplicateScanStatus').mockResolvedValue({ state: 'idle' } as never)
    const request = deferred<never>()
    const start = vi.spyOn(api, 'duplicateScan').mockReturnValue(request.promise)
    await render(<DuplicatePhotoPanel roots={roots} rootId={1} onOpenItem={() => undefined} guideTicket={1} />)
    expect(document.querySelector('.quality-action-scan.scan-guide-target')).not.toBeNull()
    await click('重新整理清單')
    expect(start).not.toHaveBeenCalled()
    await click('開始重複掃描')
    expect(document.querySelector<HTMLButtonElement>('.quality-action-scan')!.disabled).toBe(true)
    await click('掃描中')
    expect(start).toHaveBeenCalledExactlyOnceWith(1, false)
    await act(async () => request.resolve({ state: 'running', total: 1, done: 0 } as never))
  })

  it('retains the last manual summary across tabs and replaces counts rather than accumulating', async () => {
    vi.spyOn(api, 'issueStatistics').mockResolvedValue({ labels: [], items: [], total: 0 })
    const status = { enabled: true, root_id: 1, pending: 0, local_total: 2,
      state: 'local_read', last_read: null, shared_folder: '', warning: '', manual_review: false } as SharedIssueStatus
    vi.spyOn(api, 'sharedIssueStatus').mockResolvedValue(status)
    vi.spyOn(api, 'sharedIssueBackups').mockResolvedValue([])
    vi.spyOn(api, 'sharedIssueConflicts').mockResolvedValue([])
    const run = vi.spyOn(api, 'runSharedIssueSync').mockResolvedValue({ ...status,
      last_result: { root_id: 1, at: '2026-11-14', local_total: 2,
        summary: { added: 2, updated: 0, cleared: 0, conflicts: 0 }, changes: [], conflicts: [] } })
    const view = (visible: boolean) => <RetainedView visible={visible}><StatisticsView roots={roots} onOpenItem={() => undefined} onLabelsChanged={() => undefined} /></RetainedView>
    await render(view(true)); await click('立即同步')
    expect(container.textContent).toContain('新增 2 筆')
    await render(view(false)); await render(view(true))
    expect(container.textContent).toContain('新增 2 筆')
    run.mockResolvedValue({ ...status, last_result: { root_id: 1, at: '2026-11-15', local_total: 2,
      summary: { added: 0, updated: 0, cleared: 0, conflicts: 0 }, changes: [], conflicts: [] } })
    await click('立即同步')
    expect(container.textContent).toContain('新增 0 筆')
    expect(container.textContent).not.toContain('新增 2 筆')
  })
})
