import { describe, expect, it, vi } from 'vitest'
import { loadPrivateSheetListOnce } from './privateSheetAutoLoad'
import type { PrivateSheet } from './types'

const sample: PrivateSheet[] = [{ id: 'sheet-1', name: '測試試算表' }]

describe('private Google Sheets list auto load', () => {
  it('loads the authorized list and finishes loading without changing selection', async () => {
    const onSheets = vi.fn()
    const onError = vi.fn()
    const onLoading = vi.fn()
    loadPrivateSheetListOnce(async () => sample, onSheets, onError, onLoading)
    await vi.waitFor(() => expect(onSheets).toHaveBeenCalledWith(sample))
    expect(onLoading).toHaveBeenNthCalledWith(1, true)
    expect(onLoading).toHaveBeenLastCalledWith(false)
    expect(onError).not.toHaveBeenCalled()
  })

  it('ignores late responses after tab exit or logout', async () => {
    const onSheets = vi.fn()
    const onError = vi.fn()
    const onLoading = vi.fn()
    let complete!: (value: PrivateSheet[]) => void
    const fetch = () => new Promise<PrivateSheet[]>((resolve) => { complete = resolve })
    const dispose = loadPrivateSheetListOnce(fetch, onSheets, onError, onLoading)
    dispose()
    complete(sample)
    await Promise.resolve()
    await Promise.resolve()
    expect(onSheets).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
    expect(onLoading).toHaveBeenCalledTimes(1)
  })

  it('shows fetch errors while leaving retry available', async () => {
    const onSheets = vi.fn()
    const onError = vi.fn()
    const onLoading = vi.fn()
    loadPrivateSheetListOnce(
      async () => { throw new Error('Google 暫時無法連線') },
      onSheets, onError, onLoading,
    )
    await vi.waitFor(() => expect(onError).toHaveBeenCalledOnce())
    expect(onSheets).not.toHaveBeenCalled()
    expect(onLoading).toHaveBeenLastCalledWith(false)
  })
})
