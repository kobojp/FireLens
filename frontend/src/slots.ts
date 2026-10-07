import type { ItemDetail, PhotoRecord } from './types'

export function photosForSlot(item: ItemDetail, slot: string): PhotoRecord[] {
  return item.photos.filter((photo) => photo.slot === slot)
}

export function unmappedPhotos(item: ItemDetail): PhotoRecord[] {
  return item.photos.filter((photo) => photo.slot === null)
}

export function slotAllowsAdditional(item: ItemDetail, slot: string): boolean {
  return true
}
