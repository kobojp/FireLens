import { useState } from 'react'
import type { SharedSyncResult } from './types'

const kinds: Record<string, string> = { added: '新增', updated: '更新', cleared: '清除' }

export function SyncResultPanel({ result }: { result: SharedSyncResult }) {
  const [filter, setFilter] = useState('')
  const rows = result.changes.filter(row => !filter || row.kind === filter)
  const conflicts = !filter || filter === 'conflict' ? result.conflicts : []
  return <section className="sync-result" aria-label="最近一次同步結果">
    <p role="status" className="sync-summary">
      本次同步：新增 {result.summary.added} 筆｜更新 {result.summary.updated} 筆｜
      清除 {result.summary.cleared} 筆｜衝突 {result.summary.conflicts} 筆
    </p>
    <p>本機異常設備總數 {result.local_total} 台 · 本次本機讀取：{result.at}</p>
    <p className="help-text">此摘要只計算本次實際套用的設備異常變更；未套用的衝突另列。
      雲端傳輸與其他電腦是否收到資料，仍須在 Google Drive 確認。</p>
    <details>
      <summary>查看本次變更明細（{result.changes.length} 筆，待處理衝突 {result.conflicts.length} 筆）</summary>
      <label>變更種類 <select value={filter} onChange={event => setFilter(event.target.value)}>
        <option value="">全部</option>
        {Object.entries(kinds).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        <option value="conflict">衝突</option>
      </select></label>
      <div className="result-table-wrap"><table className="result-table">
        <thead><tr><th>變更</th><th>設備類別／編號</th><th>棟別／安全相對路徑</th><th>同步前 → 同步後</th><th>來源裝置／事件時間</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.path}>
          <td>{kinds[row.kind]}</td><td>{row.category_name}／{row.code}</td>
          <td>{row.building || '位置未取得'}<small className="sync-path">{row.path}</small></td>
          <td>{row.before || '無異常'} → {row.after || '無異常'}</td>
          <td>{row.device?.slice(0, 8) || '裝置未取得'}<small className="sync-path">{row.at}</small></td>
        </tr>)}{conflicts.map(conflict => <tr key={conflict.key}>
          <td>版本衝突（尚未套用）</td>
          <td>{conflict.kind === 'label' ? '異常分類' : String(conflict.candidates[0]?.value.code ?? '設備名稱未取得')}</td>
          <td>{conflict.kind === 'issue' ? String(conflict.candidates[0]?.value.path ?? '') : '共用分類'}</td>
          <td>{conflict.candidates.map(candidate => candidate.label_name).join(' ↔ ')}</td>
          <td>{conflict.candidates.map(candidate => <small className="sync-path" key={candidate.event_id}>
            {candidate.device.slice(0, 8)} · {candidate.at}
          </small>)}</td>
        </tr>)}</tbody>
      </table></div>
      {!rows.length && !conflicts.length && <p>{result.changes.length || result.conflicts.length ? '沒有符合此種類的變更。' : '本次沒有新的設備異常變更。'}</p>}
    </details>
  </section>
}
