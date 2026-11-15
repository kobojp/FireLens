import type { ItemDetail, PhotoRecord } from './types'
import { photosForSlot, unmappedPhotos } from './slots'

/** Navigate only photos already loaded for the selected device, in visible slot order. */
export function previewPhotosForItem(item: ItemDetail | null, orderedSlots: readonly string[]): PhotoRecord[] {
  if (!item) return []
  const seen = new Set<number>()
  return [...orderedSlots.flatMap(slot => photosForSlot(item, slot)), ...unmappedPhotos(item)]
    .filter(photo => {
      if (seen.has(photo.id)) return false
      seen.add(photo.id)
      return true
    })
}

export function adjacentPreviewPhoto(photos: readonly PhotoRecord[], photoId: number, delta: -1 | 1): PhotoRecord | null {
  const index = photos.findIndex(photo => photo.id === photoId)
  return index >= 0 ? photos[index + delta] ?? null : null
}
