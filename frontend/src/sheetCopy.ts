/** Google Sheets clipboard selection and TSV formatting. */
export type SheetSelection =
  | { kind: 'column', column: number }
  | { kind: 'range', anchorRow: number, anchorColumn: number, endRow: number, endColumn: number }

export type CopyBounds = {
  startRow: number, endRow: number, startColumn: number, endColumn: number
}

export const COPY_MAX_ROWS = 20000
export const COPY_MAX_CELLS = 100000
export const COPY_BATCH_ROWS = 200

export function columnName(column: number): string {
  if (!Number.isInteger(column) || column < 1 || column > 30) throw new Error('無效的欄位')
  let name = ''
  while (column) {
    column--
    name = String.fromCharCode(65 + column % 26) + name
    column = Math.floor(column / 26)
  }
  return name
}

export function boundsFor(
  selection: SheetSelection, totalRows: number, includeHeader: boolean,
): CopyBounds {
  if (!Number.isInteger(totalRows) || totalRows < 1) {
    throw new Error('無法取得工作表總列數')
  }
  if (selection.kind === 'column' && totalRows > COPY_MAX_ROWS) {
    throw new Error('此工作表超過 20,000 列整欄複製上限，請縮小範圍或用 Google 原生編輯器')
  }
  const bounds: CopyBounds = selection.kind === 'column'
    ? { startRow: includeHeader ? 1 : 2, endRow: totalRows,
        startColumn: selection.column, endColumn: selection.column }
    : {
        startRow: Math.min(selection.anchorRow, selection.endRow),
        endRow: Math.max(selection.anchorRow, selection.endRow),
        startColumn: Math.min(selection.anchorColumn, selection.endColumn),
        endColumn: Math.max(selection.anchorColumn, selection.endColumn),
      }
  const rows = Math.max(0, bounds.endRow - bounds.startRow + 1)
  const columns = bounds.endColumn - bounds.startColumn + 1
  if (bounds.startColumn < 1 || bounds.endColumn > 30 ||
      bounds.startRow < 1 || bounds.endRow > COPY_MAX_ROWS ||
      rows * columns > COPY_MAX_CELLS) {
    throw new Error('選取超過 100,000 格，請縮小範圍後再複製')
  }
  return bounds
}

export function boundsLabel(bounds: CopyBounds): string {
  return columnName(bounds.startColumn) + bounds.startRow + ':' +
    columnName(bounds.endColumn) + bounds.endRow
}

export function inSelection(selection: SheetSelection | null, row: number, col: number): boolean {
  if (!selection) return false
  if (selection.kind === 'column') return selection.column === col
  return row >= Math.min(selection.anchorRow, selection.endRow) &&
    row <= Math.max(selection.anchorRow, selection.endRow) &&
    col >= Math.min(selection.anchorColumn, selection.endColumn) &&
    col <= Math.max(selection.anchorColumn, selection.endColumn)
}

function escapeTsvCell(value: string): string {
  if (/["\t\n\r]/.test(value)) return '"' + value.replace(/"/g, '""') + '"'
  return value
}

export function tsvFromRows(rows: string[][]): string {
  return rows.map((row) => row.map((cell) => escapeTsvCell(cell)).join('\t')).join('\n')
}

export function trimTrailingBlankRows(rows: string[][]): string[][] {
  let end = rows.length
  while (end > 0 && rows[end - 1].every((cell) => cell === '')) end--
  return rows.slice(0, end)
}

/**
 * Read every row of a selected rectangle in bounded requests. Never expose a
 * partial clipboard result when a remote read fails or selection is cancelled.
 */
export async function loadCopyRows(
  bounds: CopyBounds,
  fetchChunk: (startRow: number, endRow: number) => Promise<string[][]>,
  isCancelled: () => boolean,
  onProgress: (loaded: number, total: number) => void,
): Promise<string[][]> {
  const width = bounds.endColumn - bounds.startColumn + 1
  const total = bounds.endRow - bounds.startRow + 1
  if (total <= 0 || width < 1 || total * width > COPY_MAX_CELLS) {
    throw new Error('選取範圍無法完整複製，請縮小範圍')
  }
  const result: string[][] = []
  for (let row = bounds.startRow; row <= bounds.endRow; row += COPY_BATCH_ROWS) {
    if (isCancelled()) throw new Error('複製已取消')
    const end = Math.min(row + COPY_BATCH_ROWS - 1, bounds.endRow)
    const chunk = await fetchChunk(row, end)
    if (isCancelled()) throw new Error('複製已取消')
    if (chunk.length !== end - row + 1 ||
        chunk.some((cells) => cells.length !== width || cells.some((v) => typeof v !== 'string'))) {
      throw new Error('Google 回傳資料不完整，已取消複製')
    }
    result.push(...chunk)
    onProgress(result.length, total)
  }
  return result
}
