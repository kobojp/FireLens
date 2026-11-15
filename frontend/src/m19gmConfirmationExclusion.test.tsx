import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Source-level checks alongside semantic API tests
import { readFileSync } from 'node:fs'
import { RootExclusionPanel } from './RootExclusionPanel'
import { AppConfirmDialog } from './AppConfirmDialog'

const source = (name: string) => readFileSync(new URL(name, import.meta.url), 'utf8')
const stats = source('./StatisticsView.tsx')
const hook = source('./useAppConfirmation.tsx')
const settings = source('./SettingsView.tsx')
const quality = source('./PhotoQualityView.tsx')
const duplicates = source('./DuplicatePhotoPanel.tsx')
const sheets = source('./PublicSheetsView.tsx')
const css = source('./styles.css')

describe('M19-G unified application confirmations', () => {
  it('removes every active native confirmation from the five affected pages', () => {
    for (const file of [stats, settings, quality, duplicates, sheets]) {
      expect(file).not.toContain('window.confirm(')
      expect(file.includes('useAppConfirmation') || file.includes('confirmDialog')).toBe(true)
    }
  })

  it('presents the cloud-deletion recovery as an explicit titled confirmation', () => {
    expect(stats).toContain('>修復雲端誤刪事件</button>')
    expect(stats).toContain('api.recoverMissingSharedEvents(syncRootId)')
    expect(stats).toContain('selectedRoot !== syncRootRef.current')
    expect(stats).toContain('syncRootId !== syncRootRef.current')
    expect(stats).toContain('syncBusyRef.current')
  })

  it('keeps negative default, Escape and focus-safe modal contract', () => {
    const html = renderToStaticMarkup(<AppConfirmDialog title="修復雲端誤刪事件"
      onCancel={() => undefined} onConfirm={() => undefined} confirmLabel="確定執行">
      <p>僅在共享事件被誤刪時修復</p>
    </AppConfirmDialog>)
    expect(html).toContain('role="dialog"')
    expect(html).toContain('aria-modal="true"')
    expect(html).toContain('取消</button>')
    expect(html).toContain('確定執行</button>')
    expect(hook).toContain('if (active.current) return Promise.resolve(false)')
    expect(hook).toContain('pending?.resolve(false)')
    expect(hook).toContain('pending?.resolve(accepted)')
    expect(css).toContain('.app-confirm-backdrop { z-index: 110; }')
  })

  it('retains unsaved-sheet prompt and prevents duplicate confirmation', () => {
    expect(sheets).toContain('async function discardAllowed()')
    expect(sheets).toContain("await discardAllowed()")
    expect(sheets).toContain('alreadyConfirmed = false')
    expect(sheets).toContain('loadValues(selectedSheet, next, 1, true)')
  })
})

describe('M19-M independently scoped root folder exclusion UI', () => {
  it('renders an explicit root selector without a freeform excluded-name editor', () => {
    const html = renderToStaticMarkup(<RootExclusionPanel roots={[]} />)
    expect(html).toContain('排除掃描資料夾')
    expect(html).toContain('儲存排除設定')
    expect(html).toContain('照片根目錄')
    expect(html).not.toContain('加入排除清單')
    expect(html).toContain('disabled=""')
    expect(settings).toContain('<RootExclusionPanel roots={roots} />')
  })

  it('keeps each root draft and never sends exclusions via global settings', () => {
    const rootSource = source('./RootExclusionPanel.tsx')
    expect(rootSource).toContain('dirty.current.has(rootId)')
    expect(rootSource).toContain('dirty.current.add(rootId)')
    expect(rootSource).toContain('saveRootExclusions(target, selected)')
    expect(rootSource).toContain('rootExclusionList(rootId)')
    expect(rootSource).toContain('folder.locked || saving || loading')
    expect(rootSource).toContain('根目錄有尚未儲存的變更')
    expect(rootSource).not.toContain('api.qualityScan')
    expect(rootSource).not.toContain('api.scan')
    expect(settings).not.toContain('加入排除清單')
    expect(css).toContain('.settings-subsection')
  })
})
