import type { QualityJob } from './types'

export function qualityProgress(job: QualityJob, nowSeconds: number): {
  percent: number | null; remaining: string; phase: string
} {
  const running = job.state === 'running'
  const indexing = running && job.phase === 'indexing'
  const total = Math.max(0, job.total || 0)
  const done = Math.min(total, Math.max(0, job.done || 0))
  const percent = indexing || (running && total === 0) ? null
    : total > 0 ? Math.round(done / total * 100) : job.state === 'completed' ? 100 : 0
  let remaining = '—'
  if (running) {
    remaining = '計算中…'
    const elapsed = nowSeconds - (job.analysis_started_at ?? nowSeconds)
    if (!indexing && total > done && done >= 5 && elapsed >= 2 && Number.isFinite(elapsed)) {
      const seconds = Math.ceil(elapsed / done * (total - done))
      if (seconds >= 0 && Number.isFinite(seconds)) {
        remaining = seconds < 60 ? `約 ${seconds} 秒` : `約 ${Math.ceil(seconds / 60)} 分鐘`
      }
    }
  }
  const phase = indexing ? '正在建立照片索引' :
    job.state === 'running' ? '正在分析圖片品質' :
    job.state === 'completed' ? '掃描完成' :
    job.state === 'cancelled' ? '已取消掃描' :
    job.state === 'error' ? '掃描失敗' : '尚未開始'
  return { percent, remaining, phase }
}
