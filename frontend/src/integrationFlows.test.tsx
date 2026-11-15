// @vitest-environment jsdom
import { act, useState } from 'react'
import { createRoot } from 'react-dom/client'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LedgerPasteSheet, blankLedgerRows } from './LedgerPasteSheet'
import { RootExclusionPanel } from './RootExclusionPanel'
import { AppConfirmDialog } from './AppConfirmDialog'
import { BackupHistoryDisclosure } from './BackupHistoryDisclosure'
import { PhotoQualityView } from './PhotoQualityView'
import { api } from './api'
import type { RootRecord, TreeNode } from './types'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
const roots = [{ id: 1, label: '甲' }, { id: 2, label: '乙' }] as RootRecord[]
async function render(node: ReactNode) { await act(async () => root.render(node)) }
async function button(text: string) {
  const target = [...document.querySelectorAll('button')].find(node => node.textContent?.includes(text))!
  expect(target).toBeTruthy(); await act(async () => target.click())
}
async function select(node: HTMLSelectElement, value: string) {
  await act(async () => { node.value = value; node.dispatchEvent(new Event('change', { bubbles: true })) })
}
beforeEach(() => { container = document.createElement('div'); container.id = 'root'; document.body.append(container); root = createRoot(container) })
afterEach(async () => { await act(async () => root.unmount()); document.body.replaceChildren(); vi.restoreAllMocks() })

describe('merged ledger, root settings and quality flows', () => {
  it('pastes two-column TSV into actual editable cells and routes keyboard undo without saving', async () => {
    const undo = vi.fn(); const save = vi.spyOn(api, 'importTextLedger')
    function Sheet() {
      const [rows, setRows] = useState(() => blankLedgerRows())
      return <LedgerPasteSheet rows={rows} onChange={setRows} onUndo={undo} onError={message => { throw new Error(message) }} />
    }
    await render(<Sheet />)
    const first = container.querySelector<HTMLInputElement>('[aria-label="第 1 列 棟別樓層"]')!
    const paste = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(paste, 'clipboardData', { value: { getData: () => '棟別樓層\t設備編號\n致德樓\t致-08-19\n中正樓\t中-B2-05' } })
    await act(async () => first.dispatchEvent(paste))
    expect(container.querySelector<HTMLInputElement>('[aria-label="第 1 列 設備編號"]')!.value).toBe('致-08-19')
    expect(container.querySelector<HTMLInputElement>('[aria-label="第 2 列 棟別樓層"]')!.value).toBe('中正樓')
    await act(async () => first.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true })))
    expect(undo).toHaveBeenCalledOnce(); expect(save).not.toHaveBeenCalled()
  })
  it('focuses single-action acknowledgment, traps Escape and restores the original input', async () => {
    function Notice() {
      const [open, setOpen] = useState(false)
      return <><input aria-label="名稱" /><button onClick={() => setOpen(true)}>名稱重複</button>
        {open && <AppConfirmDialog title="清冊名稱已存在" confirmLabel="確認" cancelLabel={null}
          onCancel={() => setOpen(false)} onConfirm={() => setOpen(false)}>請更換名稱</AppConfirmDialog>}</>
    }
    await render(<Notice />)
    const input = container.querySelector('input')!; input.focus()
    await button('名稱重複')
    expect((document.activeElement as HTMLElement).textContent).toBe('確認')
    expect(container.inert).toBe(true)
    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(container.inert).toBe(false); expect(document.activeElement).toBe(input)
  })
  it('preserves independent unsaved root drafts and saves only the selected root', async () => {
    vi.spyOn(api, 'rootExclusionList').mockImplementation(async id => ({ root_id: id, saved: [], folders: [
      { name: id === 1 ? '水帶' : '備份', present: true, locked: false, excluded: false },
    ] }))
    const save = vi.spyOn(api, 'saveRootExclusions').mockImplementation(async (id, names) => ({ root_id: id, saved: names, names, rescan_required: true }))
    const global = vi.spyOn(api, 'saveSettings')
    await render(<RootExclusionPanel roots={roots} />)
    await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click())
    await select(container.querySelector('select')!, '2')
    expect(container.textContent).toContain('備份')
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(false)
    await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click())
    await button('儲存排除設定')
    expect(save).toHaveBeenCalledExactlyOnceWith(2, ['備份']); expect(global).not.toHaveBeenCalled()
    await select(container.querySelector('select')!, '1')
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(true)
    expect(container.textContent).toContain('尚未儲存')
  })
  it('blocks exclusion save after a failed load without replacing saved data with an empty list', async () => {
    vi.spyOn(api, 'rootExclusionList').mockRejectedValue(new Error('根目錄離線'))
    const save = vi.spyOn(api, 'saveRootExclusions')
    await render(<RootExclusionPanel roots={roots} />)
    expect(container.querySelector('[role="alert"]')!.textContent).toContain('已保存設定未變更')
    await button('儲存排除設定'); expect(save).not.toHaveBeenCalled()
  })
  it('keeps disclosure open on refresh, resets on root change, and does not invent zero after failure', async () => {
    const action = vi.fn()
    const view = (id: number, unavailable = false) => <BackupHistoryDisclosure key={id} count={0} offline={false} unavailable={unavailable}>
      <button onClick={action}>復原本機</button></BackupHistoryDisclosure>
    await render(view(1))
    const details = container.querySelector('details')!; expect(details.open).toBe(false)
    details.open = true; await render(view(1)); expect(container.querySelector('details')!.open).toBe(true)
    await render(view(2, true)); expect(container.querySelector('details')!.open).toBe(false)
    expect(container.textContent).toContain('暫時無法確認'); expect(container.textContent).not.toContain('已載入 0 份')
    expect(action).not.toHaveBeenCalled()
  })
  it('loads period options from the indexed tree, applies a selection without starting a scan', async () => {
    vi.spyOn(api, 'tree').mockResolvedValue([{ type: 'category', key: 'lamp', label: '燈具', children: [
      { type: 'year', key: '2026年', label: '2026年', children: [{ type: 'period', key: '11月份更換', label: '11月份更換' }] },
    ] }] as TreeNode[])
    vi.spyOn(api, 'qualitySettings').mockResolvedValue({ sensitivity: 1 } as never)
    const gallery = vi.spyOn(api, 'qualityGallery').mockResolvedValue({ items: [], total: 0 } as never)
    vi.spyOn(api, 'qualityScanStatus').mockResolvedValue({ state: 'idle' } as never)
    const scan = vi.spyOn(api, 'qualityScan')
    await render(<PhotoQualityView roots={roots} defaultRootId={1} onOpenItem={() => undefined} />)
    const period = [...container.querySelectorAll('select')].find(node => node.textContent?.includes('全部月份／批次'))!
    expect(period.textContent).toContain('11月份更換')
    await select(period, '11月份更換')
    expect(gallery.mock.lastCall?.[1].get('period')).toBe('11月份更換')
    expect(scan).not.toHaveBeenCalled()
  })
})
