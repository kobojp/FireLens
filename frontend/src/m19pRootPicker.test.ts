import { afterEach, describe, expect, it, vi } from 'vitest'
// @ts-expect-error Node-only source contract checks
import { readFileSync } from 'node:fs'
import { chooseDesktopRootFolder, hasDesktopFolderPicker } from './rootFolderPicker'

const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const settings = readFileSync(new URL('./SettingsView.tsx', import.meta.url), 'utf8')

afterEach(() => vi.unstubAllGlobals())

describe('M19-P desktop folder picker', () => {
  it('is not available from a normal browser and reports a useful error', async () => {
    vi.stubGlobal('window', {})
    expect(hasDesktopFolderPicker()).toBe(false)
    await expect(chooseDesktopRootFolder()).rejects.toThrow('僅支援 Windows 桌面版')
  })

  it('returns selected directory but never sends it to the server', async () => {
    const choose = vi.fn().mockResolvedValue('H:\\照片\\燈具更換照片')
    vi.stubGlobal('window', { pywebview: { api: { choose_root_folder: choose } } })
    expect(hasDesktopFolderPicker()).toBe(true)
    expect(await chooseDesktopRootFolder()).toBe('H:\\照片\\燈具更換照片')
    expect(choose).toHaveBeenCalledOnce()
    expect(app).toContain('if (chosen !== null) setNewRootPath(chosen)')
    expect(app).toContain('onClick={() => void addRoot()}')
  })

  it('cancel does not overwrite existing typed root, and invalid selection fails closed', async () => {
    vi.stubGlobal('window', { pywebview: { api: { choose_root_folder: vi.fn().mockResolvedValue(null) } } })
    expect(await chooseDesktopRootFolder()).toBeNull()
    vi.stubGlobal('window', { pywebview: { api: { choose_root_folder: vi.fn().mockResolvedValue('') } } })
    await expect(chooseDesktopRootFolder()).rejects.toThrow('結果無效')
  })

  it('keeps manual toggle independent from the persistent default', () => {
    expect(app).toContain("setShowNewItem((previous) => !previous)")
    expect(app).not.toContain('api.saveSettings({ ...appSettings, new_item_panel_open: next })')
    expect(app).toContain('initialNewItemPanelOpen(settings.new_item_panel_collapsed)')
    expect(settings).toContain('checked={draft.new_item_panel_collapsed}')
  })
})
