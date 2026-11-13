import type { ReactNode } from 'react'

/**
 * Keep an already visited workspace mounted while another tab is active.
 * Do not use conditional children here: unmounting loses form/query/results state.
 */
export type RetainableTab = 'quality' | 'reconcile'
export type VisitedTabs = Record<RetainableTab, boolean>

export const initialVisitedTabs: VisitedTabs = { quality: false, reconcile: false }

export function withVisitedTab(previous: VisitedTabs, tab: string): VisitedTabs {
  if (tab !== 'quality' && tab !== 'reconcile') return previous
  return previous[tab] ? previous : { ...previous, [tab]: true }
}

export function RetainedView({ visible, children }: {
  visible: boolean
  children: ReactNode
}) {
  return (
    <div
      className="retained-view"
      hidden={!visible}
      inert={!visible}
      aria-hidden={!visible}
      style={{ display: visible ? 'contents' : 'none' }}
    >
      {children}
    </div>
  )
}
