import { useEffect, useRef, useState } from 'react'
import './LedgerPasteSheet.css'

export type LedgerPasteRow = { section: string; device: string }
export const MAX_LEDGER_PASTE_ROWS = 10000

export function blankLedgerRows(size = 12): LedgerPasteRow[] {
  return Array.from({ length: size }, () => ({ section: '', device: '' }))
}

export function parseLedgerPaste(text: string): string[][] {
  // Excel/Sheets TSV with escaped quotes, embedded newlines, and CRLF.
  const result: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (char === '"' && (quoted || cell === '')) {
      if (quoted && text[index + 1] === '"') { cell += '"'; index++ }
      else quoted = !quoted
    } else if (!quoted && (char === '\t' || char === '\r' || char === '\n')) {
      row.push(cell)
      cell = ''
      if (char !== '\t') {
        result.push(row)
        row = []
        if (char === '\r' && text[index + 1] === '\n') index++
      }
    } else cell += char
  }
  if (quoted) throw new Error('貼上的清冊有未關閉的引號，請重新複製')
  if (cell || row.length) { row.push(cell); result.push(row) }
  return result.filter(values => values.some(value => value.trim()))
}

export function pasteLedgerCells(
  rows: LedgerPasteRow[], paste: string, startRow = 0, startColumn: 0 | 1 = 0,
): LedgerPasteRow[] {
  let matrix = parseLedgerPaste(paste)
  if (!matrix.length) return rows
  // Excel often copies a header row; accept both Chinese and English headers.
  const headingA = matrix[0]?.[0]?.trim().replace(/^\uFEFF/, '')
  const headingB = matrix[0]?.[1]?.trim()
  if ((['棟別樓層', '區段', '棟別／樓層'].includes(headingA)
    && ['設備編號', '編號', '設備名稱'].includes(headingB))
    || (matrix[0]?.length === 1 && ['設備編號', '編號', '設備名稱'].includes(headingA))) {
    matrix = matrix.slice(1)
  }
  if (!matrix.length) return rows
  const oneColumnDevice = startColumn === 0 && matrix.every(values => values.length === 1)
  if (matrix.some(values => values.length + (oneColumnDevice ? 1 : startColumn) > 2)) {
    throw new Error('請只複製「棟別樓層＋設備編號」兩欄，或單欄設備編號')
  }
  if (startRow + matrix.length > MAX_LEDGER_PASTE_ROWS) {
    throw new Error('單次最多 10,000 列，請分批整理清冊')
  }
  const count = Math.min(MAX_LEDGER_PASTE_ROWS, Math.max(rows.length, startRow + matrix.length + 2))
  const next = Array.from({ length: count }, (_, n) => ({ ...(rows[n] ?? { section: '', device: '' }) }))
  for (const [offset, values] of matrix.entries()) {
    const column = oneColumnDevice ? 1 : startColumn
    for (const [position, value] of values.entries()) {
      next[startRow + offset][column + position === 0 ? 'section' : 'device'] = value.replace(/[\r\n\t]+/g, ' ').trim()
    }
  }
  return next
}

export function serializeLedgerRows(rows: LedgerPasteRow[]): string {
  return rows.filter(row => row.section.trim() || row.device.trim()).map(row =>
    row.section.trim() ? `${row.section.trim()}\t${row.device.trim()}` : row.device.trim(),
  ).join('\n')
}

export function filledLedgerCount(rows: LedgerPasteRow[]): number {
  return rows.filter(row => row.section.trim() || row.device.trim()).length
}

type Cell = [number, 0 | 1]

export function LedgerPasteSheet({ rows, onChange, onUndo, onError, disabled = false }: {
  rows: LedgerPasteRow[]
  onChange: (value: LedgerPasteRow[]) => void
  onUndo: () => void
  onError: (message: string) => void
  disabled?: boolean
}) {
  const [anchor, setAnchor] = useState<Cell>([0, 0])
  const [end, setEnd] = useState<Cell>([0, 0])
  const [page, setPage] = useState(0)
  const dragging = useRef(false)
  const moving = useRef(false)
  const table = useRef<HTMLTableElement>(null)
  // Bound the DOM for large imported sheets; preserve all rows in memory.
  const pageSize = 200
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const currentPage = Math.min(page, pageCount - 1)
  const firstRow = currentPage * pageSize
  const lastRow = Math.min(rows.length, firstRow + pageSize)
  const lowRow = Math.min(anchor[0], end[0])
  const highRow = Math.max(anchor[0], end[0])
  const lowCol = Math.min(anchor[1], end[1])
  const highCol = Math.max(anchor[1], end[1])

  useEffect(() => {
    const release = () => { dragging.current = false }
    window.addEventListener('mouseup', release)
    return () => window.removeEventListener('mouseup', release)
  }, [])

  function moveTo(row: number, col: number, extend: boolean) {
    if (row < 0 || row >= rows.length || col < 0 || col > 1) return
    const target = Math.floor(row / pageSize)
    if (target !== currentPage) setPage(target)
    moving.current = true
    // For cross-page focus, ask browser to focus after the next render.
    const focus = () => {
      table.current?.querySelector<HTMLInputElement>(`[data-cell="${row},${col}"]`)?.focus()
      moving.current = false
    }
    if (target !== currentPage) window.requestAnimationFrame(focus)
    else focus()
    if (!extend) setAnchor([row, col as 0 | 1])
    setEnd([row, col as 0 | 1])
  }

  function clearSelected() {
    const next = rows.map(item => ({ ...item }))
    for (let index = lowRow; index <= highRow; index += 1) {
      if (lowCol === 0) next[index].section = ''
      if (highCol === 1) next[index].device = ''
    }
    onChange(next)
  }

  return <div className="ledger-sheet">
    <p className="help-text">從 Excel／Google 試算表複製「棟別樓層、設備編號」兩欄，點 A1 按 Ctrl＋V；只有設備編號的單欄清單也能貼上。貼上後可逐格修改，按「解析預覽」才檢查清冊。</p>
    <div className="ledger-sheet-scroll">
      <table className="ledger-sheet-table" ref={table} aria-label="貼上清冊試算表"
        onCopy={event => {
          if (lowRow === highRow && lowCol === highCol) return
          event.preventDefault()
          event.clipboardData.setData('text/plain',
            rows.slice(lowRow, highRow + 1).map(item =>
              [item.section, item.device].slice(lowCol, highCol + 1).join('\t'),
            ).join('\n'))
        }}>
        <thead><tr><th className="ledger-sheet-index">列</th><th>Ａ　棟別樓層（可空）</th><th>Ｂ　設備編號（必填）</th></tr></thead>
        <tbody>{rows.slice(firstRow, lastRow).map((row, position) => {
          const rowNo = firstRow + position
          return <tr key={rowNo}>
            <th className="ledger-sheet-index" scope="row">{rowNo + 1}</th>
            {([row.section, row.device] as const).map((value, column) =>
              <td key={column}
                className={rowNo >= lowRow && rowNo <= highRow && column >= lowCol && column <= highCol ? 'ledger-cell-selected' : ''}
                onMouseDown={event => { dragging.current = true; if (!event.shiftKey) setAnchor([rowNo, column as 0 | 1]); setEnd([rowNo, column as 0 | 1]) }}
                onMouseEnter={event => { if (dragging.current && event.buttons === 1) setEnd([rowNo, column as 0 | 1]) }}>
                <input type="text" data-cell={`${rowNo},${column}`} disabled={disabled}
                  aria-label={`第 ${rowNo + 1} 列 ${column ? '設備編號' : '棟別樓層'}`}
                  value={value} placeholder={rowNo === 0 ? (column ? '例：動-01-15' : '例：致德樓8F') : ''}
                  onFocus={() => { if (!dragging.current && !moving.current) { setAnchor([rowNo, column as 0 | 1]); setEnd([rowNo, column as 0 | 1]) } }}
                  onChange={event => {
                    const next = rows.map(item => ({ ...item }))
                    next[rowNo][column ? 'device' : 'section'] = event.target.value
                    onChange(next)
                  }}
                  onPaste={event => {
                    event.preventDefault()
                    try {
                      const clipboard = event.clipboardData.getData('text/plain')
                      const next = pasteLedgerCells(rows, clipboard, rowNo, column as 0 | 1)
                      onChange(next)
                      const inserted = parseLedgerPaste(clipboard)
                      setAnchor([rowNo, column as 0 | 1])
                      setEnd([Math.min(MAX_LEDGER_PASTE_ROWS - 1, rowNo + Math.max(0, inserted.length - 1)),
                        inserted.every(values => values.length === 1) ? 1 : Math.min(1, column + 1) as 0 | 1])
                    } catch (error) { onError(error instanceof Error ? error.message : String(error)) }
                  }}
                  onKeyDown={event => {
                    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
                      event.preventDefault(); onUndo(); return
                    }
                    if (event.key === 'Delete') { event.preventDefault(); clearSelected(); return }
                    const steps: Record<string, [number, number]> = {
                      ArrowDown: [1, 0], ArrowUp: [-1, 0],
                      ArrowLeft: [0, -1], ArrowRight: [0, 1], Enter: [1, 0],
                    }
                    if (steps[event.key]) {
                      event.preventDefault()
                      const [dr, dc] = steps[event.key]
                      moveTo(end[0] + dr, end[1] + dc, event.shiftKey)
                    } else if (event.key === 'Tab') {
                      event.preventDefault()
                      const target = rowNo * 2 + column + (event.shiftKey ? -1 : 1)
                      if (target >= 0 && target < rows.length * 2) {
                        moveTo(Math.floor(target / 2), target % 2, false)
                      }
                    }
                  }}
                />
              </td>,
            )}
          </tr>
        })}</tbody>
      </table>
    </div>
    {pageCount > 1 && <nav className="ledger-sheet-pagination" aria-label="貼上表格分頁">
      <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>上一批</button>
      <span>第 {currentPage + 1}／{pageCount} 頁 · 目前 {firstRow + 1}～{lastRow} 列</span>
      <button type="button" disabled={currentPage === pageCount - 1} onClick={() => setPage(currentPage + 1)}>下一批</button>
    </nav>}
  </div>
}
