import type { ItemDetail, PhotoRecord } from './types'
/** The same slot choices for the photo wall and unmapped-photo quick actions. */
export function displaySlotsForItem(item: ItemDetail | null, preferred?: readonly string[]): string[] {
  if (!item) return []
  const base = preferred && preferred.length === item.slots.length ? preferred : item.slots
  return [...base, ...(item.custom_slots ?? [])]
}


export function photosForSlot(item: ItemDetail, slot: string): PhotoRecord[] {
  return item.photos.filter((photo) => photo.slot === slot)
}

export function unmappedPhotos(item: ItemDetail): PhotoRecord[] {
  return item.photos.filter((photo) => photo.slot === null)
}

export function slotAllowsAdditional(item: ItemDetail, slot: string): boolean {
  return true
}

/** Photo-wall order only: never traverse a different equipment or root. */
export function photosInDisplayOrder(item: ItemDetail, slots: string[]): PhotoRecord[] {
  const seen = new Set<number>()
  return [...slots.flatMap(slot => photosForSlot(item, slot)), ...unmappedPhotos(item)]
    .filter(photo => { if (seen.has(photo.id)) return false; seen.add(photo.id); return true })
}
