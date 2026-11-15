import { describe, expect, it } from 'vitest'
import { initialNewItemPanelOpen, newItemPanelButtonText } from './newItemPanel'

describe('new item panel preference', () => {
  it('defaults to collapsed for fresh or upgraded profiles without explicit new preference', () => {
    expect(initialNewItemPanelOpen(undefined)).toBe(false)
    expect(initialNewItemPanelOpen(true)).toBe(false)
    expect(initialNewItemPanelOpen(false)).toBe(true)
  })

  it('provides explicit expanded, collapsed and no-root labels', () => {
    expect(newItemPanelButtonText(true, true)).toBe('收合新增編號資料夾')
    expect(newItemPanelButtonText(false, true)).toContain('點此展開')
    expect(newItemPanelButtonText(true, false)).toContain('請先選擇根目錄')
  })
})
