import { useCallback, useEffect, useRef, useState } from 'react'
import { AppConfirmDialog } from './AppConfirmDialog'

type Request = { title: string; message: string; confirmLabel: string; resolve: (accepted: boolean) => void }

/** One asynchronous, application-styled confirmation per mounted page. */
export function useAppConfirmation() {
  const [request, setRequest] = useState<Request | null>(null)
  const active = useRef<Request | null>(null)

  const dismiss = useCallback((accepted: boolean) => {
    const pending = active.current
    active.current = null
    setRequest(null)
    pending?.resolve(accepted)
  }, [])

  const confirmAction = useCallback((message: string, title = '請確認此操作', confirmLabel = '確定執行'): Promise<boolean> => {
    if (active.current) return Promise.resolve(false)
    return new Promise(resolve => {
      const pending = { title, message, confirmLabel, resolve }
      active.current = pending
      setRequest(pending)
    })
  }, [])

  // Never execute a dangerous action after changing pages.
  const cancelConfirmation = useCallback(() => dismiss(false), [dismiss])
  useEffect(() => () => {
    const pending = active.current
    active.current = null
    pending?.resolve(false)
  }, [])

  const confirmationDialog = request && (
    <AppConfirmDialog title={request.title} confirmLabel={request.confirmLabel}
      onCancel={cancelConfirmation} onConfirm={() => dismiss(true)}>
      <p style={{ whiteSpace: 'pre-line' }}>{request.message}</p>
    </AppConfirmDialog>
  )
  return { confirmAction, cancelConfirmation, confirmationDialog }
}
