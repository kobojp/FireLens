import type { LedgerRecord } from './types'

/** Match the Unicode NFKC / case-insensitive ledger-name uniqueness rule. */
export function ledgerNameInUse(name: string, ledgers: readonly Pick<LedgerRecord, 'name'>[]): boolean {
  const key = name.trim().normalize('NFKC').toLowerCase()
  return key.length > 0 && ledgers.some(row => row.name.trim().normalize('NFKC').toLowerCase() === key)
}

/** Import-name collision from the server, including races after client validation. */
export function isLedgerNameConflict(error: unknown): boolean {
  return error instanceof Error && /清冊名稱已存在|清冊名稱重複/u.test(error.message)
}
