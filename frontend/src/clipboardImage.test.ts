import { describe, expect, it } from 'vitest'
import { clipboardFile, clipboardHasImage, fromPaste } from './clipboardImage'

describe('clipboard image selection', () => {
  it('accepts a pasted PNG and preserves bytes', async () => {
    const blob = new File([new Uint8Array([137,80,78,71])], 'source.png', { type: 'image/png' })
    const items = [{ kind: 'file', type: 'image/png', getAsFile: () => blob }] as unknown as DataTransferItemList
    const file = fromPaste(items)
    expect(file?.name).toBe('LINE-clipboard.png')
    expect(Array.from(new Uint8Array(await file!.arrayBuffer()))).toEqual([137,80,78,71])
  })
  it('does not treat text and URLs as photos', () => {
    expect(fromPaste([{kind: 'string', type: 'text/plain', getAsFile: () => null}] as unknown as DataTransferItemList)).toBeNull()
    expect(clipboardHasImage([{types:['text/plain']}])).toBe(false)
  })
  it('enables button only for supported image MIME', () => {
    expect(clipboardHasImage([{types:['image/png']}])).toBe(true)
    expect(clipboardHasImage([{types:['image/bmp']}])).toBe(false)
    expect(clipboardFile(new File(['x'], 'x.txt', {type:'text/plain'}))).toBeNull()
    expect(clipboardFile(new File([], 'empty.png', {type:'image/png'}))).toBeNull()
  })
})
