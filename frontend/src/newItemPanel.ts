export function initialNewItemPanelOpen(saved: boolean | undefined): boolean {
  return saved ?? true
}

export function newItemPanelButtonText(expanded: boolean, rootSelected: boolean): string {
  if (!rootSelected) return '＋ 新增編號資料夾（請先選擇根目錄）'
  return expanded ? '收合新增編號資料夾' : '＋ 新增編號資料夾（點此展開）'
}
