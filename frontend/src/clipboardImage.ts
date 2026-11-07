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

export async function readClipboardImage(): Promise<File | null> {
  if (!navigator.clipboard?.read) throw new Error("此環境不支援讀取剪貼簿，請選擇槽位後按 Ctrl+V。")
  const entries = await navigator.clipboard.read()
  for (const entry of entries) {
    for (const mime of entry.types) {
      if (!SUPPORTED.has(mime)) continue
      const blob = await entry.getType(mime)
      return clipboardFile(blob)
    }
  }
  return null
}
