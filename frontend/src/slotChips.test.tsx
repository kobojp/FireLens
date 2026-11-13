import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Node-only source contract checks
import { readFileSync } from 'node:fs'
import {
  SlotChipEditor, moveSlot, syncRequiredOrder, validateSlotLayout, validateSlotName,
} from './SlotChipEditor'

const view = readFileSync(new URL('./SettingsView.tsx', import.meta.url), 'utf8')
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8')
const css = readFileSync(new URL('./SlotChipEditor.css', import.meta.url), 'utf8')

describe('M19-I tag-based category photo slots', () => {
  it('renders independent editable tags with drag, accessible move/edit/remove, add', () => {
    const html = renderToStaticMarkup(
      <SlotChipEditor title="滅火器 基本照片槽位" slots={['編號','藥劑','完成']}
        onChange={() => undefined}/>,
    )
    expect(html).toContain('編號')
    expect(html).toContain('藥劑')
    expect(html).toContain('完成')
    expect(html).toContain('draggable="true"')
    expect(html).toContain('滅火器 基本照片槽位：編號 向後移動')
    expect(html).toContain('滅火器 基本照片槽位：編號 向前移動')
    expect(html).toContain('滅火器 基本照片槽位：編輯 編號')
    expect(html).toContain('＋ 新增槽位')
    expect(html).toContain('基本槽位，參與缺照判定')
  })

  it('keeps optional slots separate from missing-slot checks, and order-only tags immutable', () => {
    const opt = renderToStaticMarkup(
      <SlotChipEditor title="水帶 自訂槽位（選填）" slots={['側面','壓力錶']}
        variant="optional" onChange={() => undefined}/>,
    )
    expect(opt).toContain('選填，不影響缺照判定')
    expect(opt).toContain('＋ 新增自訂槽位')
    const order = renderToStaticMarkup(
      <SlotChipEditor title="燈具 槽位顯示順序" slots={['後','前','中']}
        variant="order" onChange={() => undefined}/>,
    )
    expect(order).toContain('拖曳或按箭頭')
    expect(order).not.toContain('新增槽位')
    expect(order).not.toContain('改名')
    expect(order).not.toContain('移除')
  })

  it('moves tags and refuses invalid source or destination indices', () => {
    const base = ['前', '中', '後']
    expect(moveSlot(base, 0, 2)).toEqual(['中','後','前'])
    expect(moveSlot(base, 2, 1)).toEqual(['前','後','中'])
    expect(moveSlot(base, 0, -1)).toBe(base)
    expect(moveSlot(base, 0, 0)).toBe(base)
    expect(base).toEqual(['前','中','後'])
  })

  it('syncs ordering after basic-tag insertion, rename, removal or dragging', () => {
    expect(syncRequiredOrder(['後','前','中'], ['前','中','後'], ['前','中','後','側面']))
      .toEqual(['後','前','中','側面'])
    expect(syncRequiredOrder(['後','前','中'], ['前','中','後'], ['正面','中','後']))
      .toEqual(['後','正面','中'])
    expect(syncRequiredOrder(['後','前','中'], ['前','中','後'], ['前','後']))
      .toEqual(['後','前'])
    expect(syncRequiredOrder(['後','前','中'], ['前','中','後'], ['中','前','後']))
      .toEqual(['中','前','後'])
  })

  it('blocks empty, too long, duplicate, case-insensitive and dangerous filenames', () => {
    const basic = ['前','中','後']
    expect(validateSlotName('  ', basic)).toContain('空白')
    expect(validateSlotName('X'.repeat(21), basic)).toContain('20')
    expect(validateSlotName('前', basic)).toContain('重複')
    expect(validateSlotName('有效日期', basic, ['有效日期'])).toContain('重複')
    expect(validateSlotName('側面-1', basic)).toContain('-數字')
    expect(validateSlotName('壞/路徑', basic)).toContain('字元')
    expect(validateSlotName('測試.', basic)).toContain('句點')
    expect(validateSlotName('新槽位', basic)).toBeNull()
    expect(validateSlotName('前', basic, [], 0)).toBeNull()
  })

  it('validates basic + optional + aliases + display order atomically', () => {
    expect(validateSlotLayout(['前','中','後'], ['後','前','中'], ['側面'], [])).toBeNull()
    expect(validateSlotLayout([], [], [], [])).toContain('基本')
    expect(validateSlotLayout(['前','中','後'], ['前','中'], [], [])).toContain('順序')
    expect(validateSlotLayout(['前','中','後'], ['前','前','後'], [], [])).toContain('順序')
    expect(validateSlotLayout(['前','中','後'], ['前','中','後'], ['中'], [])).toContain('重複')
    expect(validateSlotLayout(['編號','藥劑','完成'], ['編號','藥劑','完成'], ['有效日期'], ['有效日期']))
      .toContain('重複')
  })

  it('rejects a required-slot name colliding with a different mapped filename alias', () => {
    expect(validateSlotLayout(
      ['編號','有效日期','完成'], ['編號','有效日期','完成'], [],
      { '編號': '編號', '有效日期': '藥劑' },
    )).toContain('同義詞衝突')
  })

  it('retains unsaved edits in another category during one category save and refresh', () => {
    expect(view).toContain('dirtyCategoryCodes.current.add(category.code)')
    expect(view).toContain('dirtyCategoryCodes.current.delete(code)')
    expect(view).toContain('dirtyCategoryCodes.current.has(category.code)')
    expect(view).toContain('setSlotDrafts(previous => Object.fromEntries')
    expect(view).toContain('setOrderDrafts(previous => Object.fromEntries')
    expect(view).toContain('setCustomDrafts(previous => Object.fromEntries')
  })

  it('wires per-category atomic saves, undo and non-destructive warning', () => {
    expect(view).toContain('<SlotChipEditor title={`${category.name} 基本照片槽位`}')
    expect(view).toContain('<SlotChipEditor title={`${category.name} 槽位顯示順序`}')
    expect(view).toContain('<SlotChipEditor title={`${category.name} 自訂槽位（選填）`}')
    expect(view).toContain('resetCategoryLayout(category.code)')
    expect(view).toContain('原圖與檔名不會被修改或刪除')
    expect(view).toContain('未對應照片')
    expect(view).toContain('removed.length > 0 || removedOptional.length > 0, displayOrder, optional')
    expect(view).toContain('onSettingsChanged(await api.settings())')
    expect(api).toContain('slot_order: slotOrder, custom_slots: customSlots')
    expect(view).toContain('slot_order: latest.slot_order, custom_slots: latest.custom_slots')
    expect(css).toContain('@media (max-width: 650px)')
    expect(css).toContain('html[data-theme="dark"]')
  })
})
