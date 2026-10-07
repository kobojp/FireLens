import type { OrganizerRenameCandidate, RenamePreview } from './types'

export function safeCandidateIds(rows: OrganizerRenameCandidate[]): string[] {
  return rows.filter((row) => row.safe).map((row) => row.candidate_id)
}

export function toggleCandidate(selected: string[], candidateId: string): string[] {
  const next = new Set(selected)
  if (next.has(candidateId)) next.delete(candidateId)
  else next.add(candidateId)
  return [...next]
}

export function previewCanExecute(preview: RenamePreview | null): boolean {
  if (!preview || preview.selected.length === 0) return false
  return preview.missing_candidate_ids.length === 0 && preview.blocked_count === 0
}
