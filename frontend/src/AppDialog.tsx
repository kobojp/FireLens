import { useEffect, useRef, useState } from 'react'
import type { HTMLAttributes, ReactNode } from 'react'
import { createPortal } from 'react-dom'

const layers: HTMLDivElement[] = []
let rootWasInert = false
let bodyOverflow = ''
const focusable = 'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]'

/** Shared lifecycle for every application-owned modal, including existing editors. */
export function ModalBackdrop({ children, onCancel, ...props }: HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
  onCancel: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const cancelRef = useRef(onCancel)
  cancelRef.current = onCancel
  useEffect(() => {
    const layer = ref.current!
    const previous = document.activeElement as HTMLElement | null
    const root = document.getElementById('root')
    if (!layers.length) { rootWasInert = root?.inert ?? false; bodyOverflow = document.body.style.overflow }
    const lower = layers.at(-1)
    if (lower) lower.inert = true
    layers.push(layer)
    if (root) root.inert = true
    document.body.style.overflow = 'hidden'
    const safe = layer.querySelector<HTMLElement>('[data-dialog-cancel]') ?? [...layer.querySelectorAll<HTMLButtonElement>('button')].find(button => !button.disabled && /取消|關閉|我知道了/.test(button.textContent ?? ''))
    ;(safe ?? layer.querySelector<HTMLElement>(focusable) ?? layer).focus()
    const keydown = (event: KeyboardEvent) => {
      if (layers.at(-1) !== layer) return
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopImmediatePropagation()
        cancelRef.current()
      } else if (event.key === 'Tab') {
        const nodes = [...layer.querySelectorAll<HTMLElement>(focusable)].filter(node => !node.hidden && !node.closest('[hidden]'))
        const first = nodes[0] ?? layer
        const last = nodes.at(-1) ?? layer
        if (event.shiftKey && (document.activeElement === first || !layer.contains(document.activeElement))) {
          event.preventDefault(); last.focus()
        } else if (!event.shiftKey && (document.activeElement === last || !layer.contains(document.activeElement))) {
          event.preventDefault(); first.focus()
        }
      }
    }
    document.addEventListener('keydown', keydown, true)
    return () => {
      document.removeEventListener('keydown', keydown, true)
      layers.splice(layers.indexOf(layer), 1)
      const remaining = layers.at(-1)
      if (remaining) remaining.inert = false
      else {
        if (root) root.inert = rootWasInert
        document.body.style.overflow = bodyOverflow
      }
      if (previous?.isConnected && !previous.closest('[inert]')) previous.focus()
    }
  }, [])
  const content = <div {...props} ref={ref} tabIndex={-1}>{children}</div>
  return typeof document === 'undefined' ? content : createPortal(content, document.body)
}

type Confirmation = { message: string; resolve: (value: boolean) => void }
let showConfirmation: ((value: Confirmation) => void) | null = null
let pending: Confirmation | null = null

/** Re-entry is cancelled; callers must await approval before any side effect. */
export function confirmDialog(message: string): Promise<boolean> {
  if (!showConfirmation || pending) return Promise.resolve(false)
  return new Promise(resolve => {
    pending = { message, resolve }
    showConfirmation!(pending)
  })
}

export function AppDialogHost() {
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  useEffect(() => {
    showConfirmation = setConfirmation
    return () => {
      showConfirmation = null
      pending?.resolve(false)
      pending = null
    }
  }, [])
  function finish(approved: boolean) {
    const current = pending
    pending = null
    setConfirmation(null)
    current?.resolve(approved)
  }
  if (!confirmation) return null
  return <ModalBackdrop className="preview-backdrop app-confirm-backdrop" onCancel={() => finish(false)}
    onMouseDown={event => { if (event.target === event.currentTarget) finish(false) }}>
    <section className="prompt-dialog app-confirm-dialog" role="alertdialog" aria-modal="true"
      aria-labelledby="app-confirm-title" aria-describedby="app-confirm-message">
      <div className="prompt-header" id="app-confirm-title">確認操作</div>
      <div className="prompt-body" id="app-confirm-message">{confirmation.message}</div>
      <div className="prompt-footer">
        <button type="button" data-dialog-cancel onClick={() => finish(false)}>取消</button>
        <button type="button" className="danger-button" onClick={() => finish(true)}>確認執行</button>
      </div>
    </section>
  </ModalBackdrop>
}
