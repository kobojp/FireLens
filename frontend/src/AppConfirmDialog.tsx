import { useId } from 'react'
import { ModalBackdrop } from './AppDialog'
import type { ReactNode } from 'react'

type Props = {
  title: string
  cancelLabel?: string | null
  confirmLabel: string
  disabled?: boolean
  onCancel: () => void
  onConfirm: () => void
  children: ReactNode
}

/** Accessible centered confirmation and single-action notification dialog. */
export function AppConfirmDialog({
  title, cancelLabel = '取消', confirmLabel, disabled = false, onCancel, onConfirm, children,
}: Props) {
  const titleId = useId()
  const hasCancel = cancelLabel !== null
  return (
    <ModalBackdrop className="preview-backdrop app-confirm-backdrop" role="presentation" onCancel={() => { if (!disabled) onCancel() }}
      onMouseDown={(event) => { if (event.target === event.currentTarget && !disabled) onCancel() }}>
      <section className="app-confirm-dialog" role="dialog" aria-modal="true"
        aria-labelledby={titleId} onMouseDown={event => event.stopPropagation()}>
        <header className="app-confirm-header">
          <h2 id={titleId}>{title}</h2>
          <button type="button" aria-label="關閉視窗" disabled={disabled} onClick={onCancel}>×</button>
        </header>
        <div className="app-confirm-content">{children}</div>
        <footer className="app-confirm-footer">
          {hasCancel && <button data-dialog-cancel type="button" disabled={disabled} onClick={onCancel}>{cancelLabel}</button>}
          <button data-dialog-cancel={!hasCancel || undefined} type="button" className="primary-button" disabled={disabled} onClick={onConfirm}>{confirmLabel}</button>
        </footer>
      </section>
    </ModalBackdrop>
  )
}
