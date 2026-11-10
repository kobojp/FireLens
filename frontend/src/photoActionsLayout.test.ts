import { describe, expect, it } from 'vitest'
// @ts-expect-error Node's fs is only used in Vitest, not bundled into the app.
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf-8')
const component = readFileSync(new URL('./App.tsx', import.meta.url), 'utf-8')

describe('photo tile responsive layout regression', () => {
  it('actions use CSS grid rather than inline flex and keep all four operations', () => {
    expect(component).toContain('className="photo-actions" role="group"')
    expect(component).not.toContain('className="photo-actions" style=')
    expect(component).toMatch(/換圖\s*<input/)
    expect(component).toContain('>重新命名</button>')
    expect(component).toContain('>移動／交換</button>')
    expect(component).toContain('>刪除</button>')
    expect(css).toMatch(/\.photo-actions\s*\{[^}]*display:\s*grid/s)
    expect(css).toMatch(/\.photo-actions\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s)
    expect(css).toMatch(/\.photo-actions\s*>\s*button,\s*\.photo-actions\s*>\s*label\s*\{[^}]*min-width:\s*0/s)
  })
  it('responds to card and panel size without hiding delete', () => {
    expect(css).toContain('.photo-tile { min-width: 0; container-type: inline-size; }')
    expect(css).toContain('@container (max-width: 170px)')
    expect(css).toContain('@container (min-width: 410px)')
    expect(css).toContain('.photo-panel { container-type: inline-size; }')
    expect(css).toContain('@container (max-width: 710px)')
    expect(css).toContain('@container (max-width: 430px)')
    expect(css).toMatch(/\.slot-wall\s*\{[^}]*repeat\(3,\s*minmax\(0,\s*1fr\)\)/s)
  })
})
