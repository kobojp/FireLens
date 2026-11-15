/** Windows-only folder picker; web deployments never reveal a local path. */
type DesktopFolderWindow = Window & {
  pywebview?: { api?: { choose_root_folder?: () => Promise<string | null> } }
}

export function hasDesktopFolderPicker(): boolean {
  return typeof window !== 'undefined' &&
    typeof (window as DesktopFolderWindow).pywebview?.api?.choose_root_folder === 'function'
}

export async function chooseDesktopRootFolder(): Promise<string | null> {
  const action = (window as DesktopFolderWindow).pywebview?.api?.choose_root_folder
  if (typeof action !== 'function') throw new Error('資料夾瀏覽僅支援 Windows 桌面版，可直接輸入路徑。')
  const path = await action()
  if (path === null) return null
  if (typeof path !== 'string' || !path.trim()) throw new Error('資料夾選擇結果無效，請重試。')
  return path
}
