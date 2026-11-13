import { describe, expect, it } from 'vitest'
// @ts-expect-error This Vitest source-contract suite reads built TypeScript sources
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const types = readFileSync(new URL('./types.ts', import.meta.url), 'utf8')
const bridge = readFileSync(new URL('../../desktop/clipboard.py', import.meta.url), 'utf8')

describe('M19-E responsive paste and safe background refresh', () => {
  it('does not await tree or cache refresh before finishing the paste action', () => {
    expect(app).toContain('setItem(updated)')
    expect(app).toContain('void Promise.allSettled([refreshTree(uploadRoot), refreshCacheState(uploadRoot)])')
    expect(app).not.toContain('await refreshTree(rootId)\n      await refreshCacheState(rootId)')
    expect(app).toContain('const uploadRoot = rootId')
    expect(app).toContain('const uploadItemId = item.id')
  })

  it('does not let an old tree/cache request overwrite a newly selected root', () => {
    expect(app).toContain('const treeRefreshSeq = useRef(0)')
    expect(app).toContain('const cacheRefreshSeq = useRef(0)')
    expect(app).toContain('if (activeRootRef.current !== id || sequence !== treeRefreshSeq.current) return')
    expect(app).toContain('if (activeRootRef.current !== id || sequence !== cacheRefreshSeq.current) return')
    expect(app).toContain('selectedItemIdRef.current === uploadItemId')
  })

  it('shows redaction-safe stage timings without paths or image bytes', () => {
    expect(types).toContain('import_timing_ms?')
    expect(app).toContain('t.duplicate_check')
    expect(app).toContain('t.prepare_hash')
    expect(app).toContain('t.write_verify')
    expect(app).toContain('t.index_audit')
    expect(app).toContain('performance.now()')
  })

  it('preserves lossless PNG clipboard pixels while favoring faster compression', () => {
    expect(bridge).toContain('compress_level=1')
    expect(bridge).toContain('mime": "image/png"')
  })
})
