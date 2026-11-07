import { describe, expect, it } from 'vitest'
import { extractSheetId, sheetEmbedUrl, sheetUrl } from './publicSheets'

const id = '1aBCDEfgHIJklMNOPqrstUVWXYZ12345'
describe('public sheet URL validation', () => {
  it('accepts Google Sheets URLs only', () => {
    expect(extractSheetId(`https://docs.google.com/spreadsheets/d/${id}/edit#gid=0`)).toBe(id)
    expect(extractSheetId(`https://docs.google.com/spreadsheets/d/${id}/view`)).toBe(id)
    expect(sheetUrl(id)).toBe(`https://docs.google.com/spreadsheets/d/${id}/edit`)
    expect(sheetEmbedUrl(id)).toContain('/edit?rm=minimal')
  })
  it('rejects arbitrary domains, scripts, invalid IDs', () => {
    expect(extractSheetId(`https://docs.google.com.evil.example/spreadsheets/d/${id}/edit`)).toBeNull()
    expect(extractSheetId(`javascript:alert(1)`)).toBeNull()
    expect(extractSheetId(`https://docs.google.com/spreadsheets/d/../edit`)).toBeNull()
    expect(sheetEmbedUrl('../secret')).toBeNull()
    expect(sheetUrl('bad')).toBeNull()
  })
})
