import type { ReactNode } from 'react'

type Props = {
  count: number
  offline: boolean
  unavailable?: boolean
  children: ReactNode
}

/** Native disclosure: closed on mount, accessible by mouse and keyboard. */
export function BackupHistoryDisclosure({ count, offline, unavailable = false, children }: Props) {
  return (
    <details className="shared-issue-backups" aria-label="本機歷史備份">
      <summary className="shared-issue-backup-summary">
        <strong>本機歷史備份</strong>
        <span>{offline ? '共用資料夾離線' : unavailable ? '備份清單暫時無法確認' : `已載入 ${count} 份`}（最多顯示 100 份）</span>
        <span className="shared-issue-toggle-hint">點擊展開／收合</span>
      </summary>
      <div className="shared-issue-backup-list">{children}</div>
    </details>
  )
}
