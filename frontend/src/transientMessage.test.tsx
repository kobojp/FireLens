// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api'

vi.mock('./api', () => ({ api: {
  listRoots: vi.fn(async () => [{ id: 1, label: '合成照片', path: '/synthetic' }]),
  issueLabels: vi.fn(async () => []), categories: vi.fn(async () => []),
  settings: vi.fn(async () => { throw new Error('設定讀取失敗') }),
  appInfo: vi.fn(async () => { throw new Error('無版本資訊') }),
  tree: vi.fn(async () => []),
  rootStatus: vi.fn(async () => ({ connected: true, pending_imports: 0 })),
  offlineQueue: vi.fn(async () => []),
  scanStatus: vi.fn(async () => ({ root_id: 1, state: 'idle' })),
  cacheThumbnails: vi.fn(async () => ({ created: 3, failed: 0 })),
} }))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
let mounted: boolean
const banner = () => container.querySelector('.success-banner')
async function advance(ms: number) { await act(async () => vi.advanceTimersByTime(ms)) }
async function cache() {
  const button = [...container.querySelectorAll('button')].find(node => node.textContent === '建立縮圖快取')!
  expect(button.disabled).toBe(false)
  await act(async () => button.click())
}
beforeEach(async () => {
  vi.useFakeTimers()
  container = document.createElement('div'); document.body.append(container)
  root = createRoot(container); mounted = true
  await act(async () => root.render(<App />))
})
afterEach(async () => {
  if (mounted) await act(async () => root.unmount())
  document.body.replaceChildren(); vi.useRealTimers(); vi.restoreAllMocks()
})

it('keeps actual App feedback for five seconds, then removes its banner', async () => {
  await cache()
  expect(banner()?.textContent).toContain('新增 3 張')
  await advance(4999); expect(banner()).not.toBeNull()
  await advance(1); expect(banner()).toBeNull()
})

it('restarts the deadline for a new completion without the old timer hiding it', async () => {
  await cache(); await advance(3000)
  vi.mocked(api.cacheThumbnails).mockResolvedValueOnce({ created: 7, failed: 0 } as Awaited<ReturnType<typeof api.cacheThumbnails>>)
  await cache(); await advance(2000)
  expect(banner()?.textContent).toContain('新增 7 張')
  await advance(2999); expect(banner()).not.toBeNull()
  await advance(1); expect(banner()).toBeNull()
})

it('restarts the deadline for the same message and cleans timers on unmount', async () => {
  await cache(); await advance(3000); await cache()
  await advance(2000); expect(banner()).not.toBeNull()
  await advance(3000); expect(banner()).toBeNull()
  await cache()
  expect(vi.getTimerCount()).toBeGreaterThan(0)
  await act(async () => root.unmount()); mounted = false
  expect(vi.getTimerCount()).toBe(0)
})

it('clears old feedback when a new action fails and retains the error', async () => {
  await cache()
  vi.mocked(api.cacheThumbnails).mockRejectedValueOnce(new Error('快取建立失敗，請重試'))
  await cache()
  expect(banner()).toBeNull()
  await advance(10000)
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('快取建立失敗，請重試')
  expect(vi.getTimerCount()).toBe(0)
})
