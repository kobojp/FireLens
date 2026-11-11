import { describe, expect, it } from 'vitest'
import { clipboardFile, clipboardHasImage, fromPaste, decodeDesktopClipboardImage } from './clipboardImage'
// @ts-expect-error Node fs is used by source-inspection regression tests.
import { readFileSync } from 'node:fs'

const appSource = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')

describe('clipboard image selection', () => {
  it('accepts a pasted PNG and preserves bytes', async () => {
    const blob = new File([new Uint8Array([137,80,78,71])], 'source.png', { type: 'image/png' })
    const items = [{ kind: 'file', type: 'image/png', getAsFile: () => blob }] as unknown as DataTransferItemList
    const file = fromPaste(items)
    expect(file?.name).toBe('LINE-clipboard.png')
    expect(Array.from(new Uint8Array(await file!.arrayBuffer()))).toEqual([137,80,78,71])
  })
  it('does not probe clipboard on focus and uses centered guidance in browsers', () => {
    expect(appSource).not.toContain('navigator.clipboard.read(')
    expect(appSource).not.toContain("window.addEventListener('focus'")
    expect(appSource).toContain('hasDesktopClipboardBridge()')
    expect(appSource).toContain('showPasteHelp && !pendingPaste')
    expect(appSource).toContain('role="dialog" aria-modal="true"')
    expect(appSource).toContain("window.addEventListener('paste', onPaste)")
  })
  it('does not treat text and URLs as photos', () => {
    expect(fromPaste([{kind: 'string', type: 'text/plain', getAsFile: () => null}] as unknown as DataTransferItemList)).toBeNull()
    expect(clipboardHasImage([{types:['text/plain']}])).toBe(false)
  })
  it('decodes native desktop clipboard images without clipboard-read permission', async () => {
    const encoded = btoa(String.fromCharCode(137, 80, 78, 71))
    const file = decodeDesktopClipboardImage({ mime: 'image/png', base64: encoded })
    expect(file?.type).toBe('image/png')
    expect(Array.from(new Uint8Array(await file!.arrayBuffer()))).toEqual([137,80,78,71])
    expect(decodeDesktopClipboardImage(null)).toBeNull()
    expect(() => decodeDesktopClipboardImage({ mime: 'text/plain', base64: encoded })).toThrow()
    expect(() => decodeDesktopClipboardImage({ mime: 'image/png', base64: '%%' })).toThrow()
  })
  it('enables button only for supported image MIME', () => {
    expect(clipboardHasImage([{types:['image/png']}])).toBe(true)
    expect(clipboardHasImage([{types:['image/bmp']}])).toBe(false)
    expect(clipboardFile(new File(['x'], 'x.txt', {type:'text/plain'}))).toBeNull()
    expect(clipboardFile(new File([], 'empty.png', {type:'image/png'}))).toBeNull()
  })
})
