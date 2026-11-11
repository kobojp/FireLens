import { describe, expect, it } from 'vitest'
// @ts-expect-error Node fs is used by Vitest to inspect the UI layout source.
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
const tree = readFileSync(new URL('./TreeView.tsx', import.meta.url), 'utf8')

describe('M18-G independently scrolling photo-browser columns', () => {
  it('constrains only browse mode to viewport height', () => {
    expect(app).toContain("view === 'browse' ? ' browse-layout' : ''")
    expect(css).toMatch(/\.app-shell\.browse-layout\s*\{[^}]*height:\s*100dvh;[^}]*overflow:\s*hidden/s)
    expect(css).toMatch(/\.browse-layout \.workspace\s*\{[^}]*min-height:\s*0;[^}]*overflow:\s*hidden/s)
    expect(css).not.toMatch(/(?:^|\n)\.app-shell\s*\{[^}]*overflow:\s*hidden/s)
  })

  it('keeps tree title and search static while list itself scrolls', () => {
    expect(app).toContain('className="panel tree-panel"')
    expect(app).toContain('className="tree-search"')
    expect(app).toContain('<TreeView key={rootId')
    expect(css).toMatch(/\.browse-layout \.tree-panel\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;[^}]*overflow:\s*hidden/s)
    expect(css).toMatch(/\.browse-layout \.tree-panel \.tree-view\s*\{[^}]*flex:\s*1;[^}]*overflow-y:\s*auto;[^}]*overscroll-behavior-y:\s*contain/s)
    expect(tree).toContain('tabIndex={0} role="region" aria-label="可捲動設備清單"')
    expect(css).toContain('.browse-layout .tree-panel .tree-view:focus-visible')
  })

  it('scrolls photo and information panels separately and resets photo scroll on selection', () => {
    expect(css).toMatch(/\.browse-layout \.workspace > \.panel\s*\{[^}]*overflow-y:\s*auto;[^}]*overscroll-behavior-y:\s*contain/s)
    expect(app).toContain('className="panel photo-panel" ref={photoPanelRef}')
    expect(app).toContain('if (photoPanelRef.current) photoPanelRef.current.scrollTop = 0')
    expect(app).toContain('className="panel info-panel"')
    expect(app).toContain('expandedPaths={rootId === null ? undefined : expandedByRoot[rootId]}')
  })
})
