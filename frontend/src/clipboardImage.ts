/** Clipboard image decoding shared by Ctrl+V and the Paste button. */
const SUPPORTED = new Set(["image/png", "image/jpeg", "image/heic", "image/heif"])
const EXTENSIONS: Record<string, string> = {
  "image/png": "png", "image/jpeg": "jpg",
  "image/heic": "heic", "image/heif": "heif",
}
export const MAX_CLIPBOARD_BYTES = 100 * 1024 * 1024

export function clipboardFile(file: File | Blob): File | null {
  if (!SUPPORTED.has(file.type) || !file.size || file.size > MAX_CLIPBOARD_BYTES) return null
  return new File([file], `LINE-clipboard.${EXTENSIONS[file.type]}`, { type: file.type })
}

export function fromPaste(items: DataTransferItemList | null): File | null {
  if (!items) return null
  for (const entry of Array.from(items)) {
    if (entry.kind !== "file" || !entry.type.startsWith("image/")) continue
    const file = entry.getAsFile()
    if (file) return clipboardFile(file)
  }
  return null
}

export function clipboardHasImage(items: readonly { types: readonly string[] }[]): boolean {
  return items.some((item) => item.types.some((type) => SUPPORTED.has(type)))
}

type DesktopClipboardPayload = { mime: string; base64: string }
type DesktopClipboardWindow = Window & {
  pywebview?: { api?: { read_clipboard_image?: () => Promise<DesktopClipboardPayload | null> } }
}

export function hasDesktopClipboardBridge(): boolean {
  return typeof (window as DesktopClipboardWindow).pywebview?.api?.read_clipboard_image === 'function'
}

export function decodeDesktopClipboardImage(payload: DesktopClipboardPayload | null): File | null {
  if (!payload) return null
  if (!SUPPORTED.has(payload.mime) || !payload.base64 ||
      payload.base64.length > Math.ceil(MAX_CLIPBOARD_BYTES * 4 / 3) + 8) {
    throw new Error('剪貼簿圖片格式或大小不支援')
  }
  let data: Uint8Array<ArrayBuffer>
  try {
    const binary = atob(payload.base64)
    data = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index++) data[index] = binary.charCodeAt(index)
  } catch {
    throw new Error('剪貼簿圖片資料無效')
  }
  return clipboardFile(new File([data], 'clipboard.png', { type: payload.mime }))
}

export async function readDesktopClipboardImage(): Promise<File | null> {
  const bridge = (window as DesktopClipboardWindow).pywebview?.api?.read_clipboard_image
  if (typeof bridge !== 'function') return null
  return decodeDesktopClipboardImage(await bridge())
}

