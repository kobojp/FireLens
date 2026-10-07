import { describe, expect, it } from 'vitest'
import { photosForSlot, slotAllowsAdditional, unmappedPhotos } from './slots'
import type { ItemDetail } from './types'

const item: ItemDetail = {
  id: 1,
  root_id: 1,
  category_id: 1,
  category_code: 'extinguisher',
  category_name: '滅火器',
  year: '2026年',
  period: '10月份更換',
  building: '中正樓',
  code: '中-01-01',
  relative_path: '滅火器/2026年/10月份更換/中正樓/中-01-01',
  status: 'partial',
  photo_count: 2,
  slots: ['編號', '藥劑', '完成'],
  custom_slots: [],
  filename_aliases: { 有效日期: '藥劑' },
  photos: [
    { id: 1, filename: '編號.jpg', relative_path: 'a', extension: '.jpg', slot: '編號', size_bytes: 1, mtime_ns: 1, cloud_placeholder: 0 },
    { id: 2, filename: '其他.jpg', relative_path: 'b', extension: '.jpg', slot: null, size_bytes: 1, mtime_ns: 1, cloud_placeholder: 0 },
  ],
}

describe('slot helpers', () => {
  it('groups mapped and unmapped photos', () => {
    expect(photosForSlot(item, '編號').map((photo) => photo.id)).toEqual([1])
    expect(unmappedPhotos(item).map((photo) => photo.id)).toEqual([2])
  })

  it('allows multiple extinguisher photos in a single slot', () => {
    expect(slotAllowsAdditional(item, '編號')).toBe(true)
    expect(slotAllowsAdditional(item, '藥劑')).toBe(true)
  })

  it('allows multiple photos for box slots', () => {
    const box = { ...item, category_code: 'box', slots: ['前', '中', '後'] }
    expect(slotAllowsAdditional(box, '前')).toBe(true)
  })
})
