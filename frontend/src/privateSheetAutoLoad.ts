import type { PrivateSheet } from './types'

/**
 * One guarded list fetch per authorized tab mount/auth transition.
 * Disposing it invalidates a pending response (logout/tab exit), so stale
 * Google results cannot overwrite a newer session's sheet list.
 */
export function loadPrivateSheetListOnce(
  fetchSheets: () => Promise<PrivateSheet[]>,
  onSheets: (sheets: PrivateSheet[]) => void,
  onError: (error: unknown) => void,
  onLoading: (loading: boolean) => void,
): () => void {
  let active = true
  onLoading(true)
  void fetchSheets().then((sheets) => {
    if (active) onSheets(sheets)
  }).catch((error: unknown) => {
    if (active) onError(error)
  }).finally(() => {
    if (active) onLoading(false)
  })
  return () => { active = false }
}
