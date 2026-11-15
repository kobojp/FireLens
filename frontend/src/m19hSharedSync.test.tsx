import { afterEach, describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
// @ts-expect-error Node-only contract inspection
import { readFileSync } from 'node:fs'
import { rememberSharedIssueSync, previousSharedIssueSync } from './sharedIssueSession'
import { StatisticsView } from './StatisticsView'
import type { SharedIssueStatus } from './types'

const source = readFileSync(new URL('./StatisticsView.tsx', import.meta.url), 'utf8')
const panel = readFileSync(new URL('./SyncResultPanel.tsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

const base: SharedIssueStatus = {
  enabled: true, root_id: 501, pending: 0, last_read: '2026-11-14T12:10:00Z',
  state: 'local_read', shared_folder: 'synthetic-test', warning: '', manual_review: false,
  synced_at: '2026-11-14T12:10:00Z',
  local_total: 3,
  changes: { added: 1, updated: 1, cleared: 0 },
  change_details: [{
    path: '滅火器/2026年/11月份更換/中正樓/中-01-01',
    category: 'extinguisher', category_name: '滅火器',
    code: '中-01-01', building: '中正樓', kind: 'added',
    before: null, after: '瓶身超過10年', source_device: 'aa123456',
    event_at: '2026-11-14T12:09:00Z',
  }],
}

describe('M19-H manual shared issue sync result', () => {
  afterEach(() => {
    // Store is session-only; every test uses a distinct root.
  })

  it('retains only explicit response per root, replaced rather than accumulated', () => {
    expect(previousSharedIssueSync(501)).toBeNull()
    rememberSharedIssueSync(base)
    expect(previousSharedIssueSync(501)).toEqual(base)
    expect(previousSharedIssueSync(502)).toBeNull()
    const next = { ...base, changes: { added: 0, updated: 0, cleared: 0 }, change_details: [] }
    rememberSharedIssueSync(next)
    expect(previousSharedIssueSync(501)?.changes).toEqual({ added: 0, updated: 0, cleared: 0 })
    expect(previousSharedIssueSync(null)).toBeNull()
  })

  it('renders the normal shared issue panel with no fabricated cloud-upload success', () => {
    const html = renderToStaticMarkup(<StatisticsView roots={[]} onOpenItem={() => undefined}
      onLabelsChanged={() => undefined} />)
    expect(html).toContain('Google Drive 多人異常同步與本機備份')
    expect(html).toContain('已讀取')
    expect(source).not.toContain('Google Drive 已上傳成功')
    expect(source).toContain('無法保證 Google Drive 已完成上傳')
  })

  it('shows actual local DB additions, updates, clears, conflicts, and human-readable details', () => {
    expect(panel).toContain('result.summary.added')
    expect(panel).toContain('result.summary.updated')
    expect(panel).toContain('result.summary.cleared')
    expect(panel).toContain('result.summary.conflicts')
    expect(panel).toContain('result.local_total')
    expect(source).toContain('syncStatus.pending')
    expect(panel).toContain('本次沒有新的設備異常變更')
    expect(panel).toContain('row.before ||')
    expect(panel).toContain('row.after ||')
    expect(panel).toContain('row.device?')
    expect(source).toContain('candidate.label_name')
    expect(source).not.toContain('JSON.stringify(candidate.value)')
    expect(styles).toContain('.shared-issue-run-report')
    expect(styles).toContain('details summary:focus-visible')
  })

  it('captures only direct manual sync results and ignores a root switched during a request', () => {
    expect(source).toContain('const selectedRoot = syncRootId')
    expect(source).toContain('() => api.runSharedIssueSync(syncRootId)')
    expect(source).toContain('if (selectedRoot !== syncRootRef.current) return')
    expect(source).toContain('setSyncResult(output.last_result)')
    expect(source).toContain('setSyncResult(result.last_result ?? null)')
    expect(source).toContain('syncBusyRef.current')
  })
})
