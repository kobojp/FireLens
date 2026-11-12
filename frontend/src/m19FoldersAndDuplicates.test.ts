import { describe, expect, it } from 'vitest'
// @ts-expect-error Vitest source inspection for the desktop UI.
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const settings = readFileSync(new URL('./SettingsView.tsx', import.meta.url), 'utf8')
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8')

describe('M19 dynamic folders and duplicate image confirmation UI', () => {
  it('makes newly scanned categories visible and exposes folder exclusion controls', () => {
    expect(app).toContain('api.categories()')
    expect(settings).toContain('excluded_root_folders')
    expect(settings).toContain('加入排除清單')
    expect(settings).toContain('移除排除')
  })
  it('has per-category slot editor and confirms destructive name changes', () => {
    expect(settings).toContain('saveCategorySlots')
    expect(settings).toContain('slotDrafts')
    expect(settings).toContain('照片槽位自訂')
    expect(settings).toContain('未對應照片')
    expect(settings).toContain('window.confirm')
    expect(api).toContain('confirm_unmapped')
    expect(app).toContain('setItem(await api.item(selected.id))')
  })
  it('never automatically confirms duplicate photos', () => {
    expect(app).toContain("message.startsWith('相同圖片已存在：')")
    expect(app).toContain('aria-label="確認儲存重複圖片"')
    expect(app).toContain('仍要儲存')
    expect(app).toContain('setDuplicateUpload(null)')
    expect(api).toContain("queryParams.set('allow_duplicate', 'true')")
  })
})
