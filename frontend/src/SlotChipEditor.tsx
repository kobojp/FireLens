import { useRef, useState } from 'react'
import './SlotChipEditor.css'

const INVALID_FILENAME_CHARS = /[<>:"/\\|?*\x00-\x1f]/
const NUMBER_SUFFIX = /-\d+$/

export function validateSlotName(
  input: string, existing: string[], reserved: string[] = [], index: number | null = null,
): string | null {
  const name = input.trim()
  if (!name) return '槽位名稱不可空白'
  if (name.length > 20) return '槽位名稱最多 20 字'
  if (INVALID_FILENAME_CHARS.test(name) || name.endsWith('.') || NUMBER_SUFFIX.test(name)) {
    return '槽位名稱含有檔案不可用字元、結尾句點或「-數字」'
  }
  if ([...existing.filter((_, n) => n !== index), ...reserved].some(
    candidate => candidate.toLocaleLowerCase() === name.toLocaleLowerCase(),
  )) return '同一設備類別的槽位及檔名同義詞不可重複'
  return null
}

export function moveSlot(items: string[], from: number, to: number): string[] {
  if (from < 0 || to < 0 || from >= items.length || to >= items.length || from === to) return items
  const next = [...items]
  const [entry] = next.splice(from, 1)
  next.splice(to, 0, entry)
  return next
}

export function syncRequiredOrder(
  currentOrder: string[], previous: string[], next: string[],
): string[] {
  const before = new Set(previous)
  const after = new Set(next)
  // Reorder operation: same labels, new order wins in both editors.
  if (previous.length === next.length && previous.every(item => after.has(item))) return [...next]
  const removed = previous.filter(item => !after.has(item))
  const added = next.filter(item => !before.has(item))
  const rename = removed.length === 1 && added.length === 1 && previous.length === next.length
  const retained = currentOrder
    .map(item => rename && item === removed[0] ? added[0] : item)
    .filter(item => after.has(item))
  return [...retained, ...next.filter(item => !retained.includes(item))]
}

export function validateSlotLayout(
  required: string[], order: string[], optional: string[],
  aliases: string[] | Record<string, string>,
): string | null {
  if (required.length < 1 || required.length > 30) return '基本照片槽位必須有 1～30 個'
  if (optional.length > 30) return '選填照片槽位最多 30 個'
  const aliasNames = Array.isArray(aliases) ? aliases : Object.keys(aliases)
  if (!Array.isArray(aliases) && Object.entries(aliases).some(([name, target]) =>
    required.some(slot => slot.toLocaleLowerCase() === name.toLocaleLowerCase()
      && slot.toLocaleLowerCase() !== target.toLocaleLowerCase()))) {
    return '基本槽位名稱與已存在的檔名同義詞衝突，請先調整同義詞'
  }
  for (let index = 0; index < required.length; index += 1) {
    const conflictingAliases = aliasNames.filter(name => !required.some(slot =>
      slot.toLocaleLowerCase() === name.toLocaleLowerCase(),
    ))
    const issue = validateSlotName(required[index], required, conflictingAliases, index)
    if (issue) return issue
  }
  for (let index = 0; index < optional.length; index += 1) {
    const issue = validateSlotName(optional[index], optional, [...required, ...aliasNames], index)
    if (issue) return issue
  }
  if (order.length !== required.length || new Set(order).size !== order.length
      || !order.every(item => required.includes(item))) {
    return '顯示順序必須包含全部且僅包含基本槽位'
  }
  return null
}

export type SlotChipEditorProps = {
  title: string
  slots: string[]
  onChange: (next: string[]) => void
  reserved?: string[]
  variant?: 'required' | 'optional' | 'order'
  disabled?: boolean
}

export function SlotChipEditor({
  title, slots, onChange, reserved = [], variant = 'required', disabled = false,
}: SlotChipEditorProps) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [entry, setEntry] = useState('')
  const [error, setError] = useState('')
  const dragSource = useRef<number | null>(null)
  const editable = variant !== 'order'
  const maxCount = variant === 'required' ? 30 : 30

  function resetEditor() {
    setAdding(false)
    setEditingIndex(null)
    setEntry('')
    setError('')
  }

  function commit() {
    if (!editable || disabled) return
    const index = adding ? null : editingIndex
    const reason = validateSlotName(entry, slots, reserved, index)
    if (reason) { setError(reason); return }
    const cleaned = entry.trim()
    const newItems = adding ? [...slots, cleaned] : slots.map((item, i) => i === editingIndex ? cleaned : item)
    if (newItems.length > maxCount) { setError('每類別最多 30 個槽位'); return }
    onChange(newItems)
    resetEditor()
  }

  function reorder(from: number, to: number) {
    if (!disabled) onChange(moveSlot(slots, from, to))
  }

  return (
    <div className={`slot-chip-editor slot-chip-editor-${variant}`}>
      <div className="slot-chip-editor-heading">
        <strong>{title}</strong>
        <small>{variant === 'order' ? '拖曳或按箭頭調整照片牆顯示順序' :
          variant === 'optional' ? '選填，不影響缺照判定' : '基本槽位，參與缺照判定'}</small>
      </div>
      <div className="slot-chip-list" role="group" aria-label={title}>
        {slots.map((slot, index) => (
          <div key={slot} className={`slot-chip slot-chip-${variant}`}
            draggable={!disabled}
            onDragStart={event => {
              dragSource.current = index
              event.dataTransfer.effectAllowed = 'move'
              event.dataTransfer.setData('text/plain', slot)
            }}
            onDragOver={event => { if (!disabled && dragSource.current !== null) event.preventDefault() }}
            onDrop={event => {
              event.preventDefault()
              if (dragSource.current !== null) reorder(dragSource.current, index)
              dragSource.current = null
            }}
            onDragEnd={() => { dragSource.current = null }}>
            <span className="slot-chip-grip" title="可拖曳排序" aria-hidden="true">⠿</span>
            <span className="slot-chip-label">{slot}</span>
            <button type="button" className="slot-chip-icon" disabled={disabled || index === 0}
              onClick={() => reorder(index, index - 1)}
              aria-label={`${title}：${slot} 向前移動`} title="向前移動">‹</button>
            <button type="button" className="slot-chip-icon" disabled={disabled || index === slots.length - 1}
              onClick={() => reorder(index, index + 1)}
              aria-label={`${title}：${slot} 向後移動`} title="向後移動">›</button>
            {editable && (
              <>
                <button type="button" className="slot-chip-icon" disabled={disabled}
                  onClick={() => { setEditingIndex(index); setAdding(false); setEntry(slot); setError('') }}
                  aria-label={`${title}：編輯 ${slot}`} title="改名">✎</button>
                <button type="button" className="slot-chip-icon slot-chip-remove"
                  disabled={disabled || (variant === 'required' && slots.length === 1)}
                  onClick={() => { onChange(slots.filter((_, i) => i !== index)); resetEditor() }}
                  aria-label={`${title}：移除 ${slot}`} title="移除">×</button>
              </>
            )}
          </div>
        ))}
        {editable && !adding && editingIndex === null && (
          <button type="button" className="slot-chip-add" disabled={disabled || slots.length >= maxCount}
            onClick={() => { setAdding(true); setEntry(''); setError('') }}>
            ＋ {variant === 'optional' ? '新增自訂槽位' : '新增槽位'}
          </button>
        )}
      </div>
      {editable && (adding || editingIndex !== null) && (
        <div className="slot-chip-entry">
          <label htmlFor={`slot-entry-${variant}-${title}`}>
            {adding ? '新增槽位名稱' : '修改槽位名稱'}
          </label>
          <input id={`slot-entry-${variant}-${title}`} autoFocus maxLength={30}
            value={entry} disabled={disabled} placeholder="輸入單一槽位名稱"
            onChange={event => { setEntry(event.target.value); setError('') }}
            onKeyDown={event => {
              if (event.key === 'Enter') { event.preventDefault(); commit() }
              if (event.key === 'Escape') { event.preventDefault(); resetEditor() }
            }} />
          <button type="button" className="slot-chip-confirm" disabled={disabled} onClick={commit}>確認</button>
          <button type="button" className="slot-chip-cancel" onClick={resetEditor}>取消</button>
          {error && <p className="slot-chip-error" role="alert">{error}</p>}
        </div>
      )}
    </div>
  )
}
