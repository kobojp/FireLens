// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { InspectorImageViewer } from './InspectorImageViewer'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
const images = [1, 2].map(id => ({ id, filename: `${id}.jpg`, title: `照片 ${id}`, subtitle: '合成照片', path: `synthetic/${id}.jpg`, src: `/synthetic/${id}` }))
let root: ReturnType<typeof createRoot>
let container: HTMLDivElement
const select = vi.fn()
const close = vi.fn()
const canvas = () => document.querySelector<HTMLDivElement>('.inspector-lightbox-canvas')!
const image = () => document.querySelector<HTMLImageElement>('.inspector-lightbox-canvas img')!
const stage = () => document.querySelector<HTMLDivElement>('.inspector-lightbox-stage')!
const ratio = () => Number(document.querySelector<HTMLInputElement>('[aria-label="圖片縮放"]')!.value)
const rect = (left: number, top: number, width: number, height: number) => ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON() {} })
async function render(activeId: number | null = 1) {
  await act(async () => root.render(<InspectorImageViewer images={images} activeId={activeId} onSelect={select} onClose={close} />))
}
async function load(width = 1200, height = 1800) {
  const view = canvas(); const photo = image()
  Object.defineProperties(view, { clientWidth: { configurable: true, value: 800 }, clientHeight: { configurable: true, value: 600 } })
  vi.spyOn(view, 'getBoundingClientRect').mockImplementation(() => rect(100, 80, 800, 600))
  let left = 0; let top = 0
  Object.defineProperties(view, {
    scrollLeft: { configurable: true, get: () => left, set: value => { left = Math.max(0, Math.min(value, Math.max(800, parseFloat(stage().style.width)) - 800)) } },
    scrollTop: { configurable: true, get: () => top, set: value => { top = Math.max(0, Math.min(value, Math.max(600, parseFloat(stage().style.height)) - 600)) } },
  })
  Object.defineProperties(photo, { naturalWidth: { configurable: true, value: width }, naturalHeight: { configurable: true, value: height } })
  vi.spyOn(photo, 'getBoundingClientRect').mockImplementation(() => {
    const w = parseFloat(photo.style.width) || Math.min(width, 800)
    const h = parseFloat(photo.style.height) || Math.min(height, 600)
    return rect(100 + (Math.max(800, parseFloat(stage().style.width) || 800) - w) / 2 - left,
      80 + (Math.max(600, parseFloat(stage().style.height) || 600) - h) / 2 - top, w, h)
  })
  await act(async () => photo.dispatchEvent(new Event('load')))
}
async function wheel(deltaY: number, x = 560, y = 440, deltaX = 0, deltaMode = 0) {
  const event = new WheelEvent('wheel', { deltaY, deltaX, deltaMode, clientX: x, clientY: y, cancelable: true, bubbles: true })
  await act(async () => canvas().dispatchEvent(event))
  return event
}
beforeEach(async () => {
  vi.clearAllMocks(); container = document.createElement('div'); document.body.append(container); root = createRoot(container)
  await render(); await load()
})
afterEach(async () => { await act(async () => root.unmount()); document.body.replaceChildren(); vi.restoreAllMocks() })

it.each([[1200, 1800], [2400, 900], [300, 200]])('keeps the pointed pixel fixed when enlarging a %s × %s image', async (w, h) => {
  await load(w, h)
  const before = image().getBoundingClientRect()
  const x = before.left + before.width * 0.65
  const y = before.top + before.height * 0.6
  const event = await wheel(-120, x, y)
  expect(event.defaultPrevented).toBe(true)
  const after = image().getBoundingClientRect()
  expect(after.left + after.width * 0.65).toBeCloseTo(x, 5)
  expect(after.top + after.height * 0.6).toBeCloseTo(y, 5)
  expect(after.width / before.width).toBeCloseTo(ratio(), 5)
})

it('shrinks around the same pixel and supports rapid wheel events without stale offsets', async () => {
  const original = image().getBoundingClientRect()
  const x = original.left + original.width * 0.6; const y = original.top + original.height * 0.6
  await act(async () => {
    canvas().dispatchEvent(new WheelEvent('wheel', { deltaY: -120, clientX: x, clientY: y, cancelable: true }))
    canvas().dispatchEvent(new WheelEvent('wheel', { deltaY: -120, clientX: x, clientY: y, cancelable: true }))
  })
  await wheel(120, x, y)
  const after = image().getBoundingClientRect()
  expect(after.left + after.width * 0.6).toBeCloseTo(x, 5)
  expect(after.top + after.height * 0.6).toBeCloseTo(y, 5)
})

it('respects both zoom limits, line/page wheel units and horizontal scrolling', async () => {
  for (let i = 0; i < 4; i++) await wheel(-40, 560, 440, 0, 1)
  expect(ratio()).toBe(4)
  for (let i = 0; i < 6; i++) await wheel(1, 560, 440, 0, 2)
  expect(ratio()).toBe(0.5)
  expect((await wheel(20, 560, 440, 80)).defaultPrevented).toBe(false)
  expect(ratio()).toBe(0.5)
})

it('keeps the slider and keyboard navigation, resets on the next image and reopening', async () => {
  await wheel(-120)
  const slider = document.querySelector<HTMLInputElement>('[aria-label="圖片縮放"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(slider, '2')
    slider.dispatchEvent(new Event('input', { bubbles: true })); slider.dispatchEvent(new Event('change', { bubbles: true }))
  })
  expect(ratio()).toBe(2)
  await act(async () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })))
  expect(select).toHaveBeenCalledWith(2)
  await render(2); await load(2400, 900)
  expect(ratio()).toBe(1); expect(canvas().scrollLeft).toBe(0); expect(canvas().scrollTop).toBe(0)
  await wheel(-120); await render(null); await render(1); await load()
  expect(ratio()).toBe(1)
})

it('does not intercept wheel events after a photo load error or viewer close', async () => {
  const view = canvas()
  await act(async () => image().dispatchEvent(new Event('error')))
  expect((await wheel(-120)).defaultPrevented).toBe(false)
  await render(null)
  const event = new WheelEvent('wheel', { deltaY: -120, cancelable: true })
  view.dispatchEvent(event); expect(event.defaultPrevented).toBe(false)
})
