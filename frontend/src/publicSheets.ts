/** Only permit Google Sheets IDs for iframe and external navigation. */
const SHEET_ID = /^[A-Za-z0-9_-]{10,160}$/
export const PUBLIC_FOLDER_ID = '1iEgsrIVmFdwC4sgLjDWOZZSfA9-xNgpU'
export const PUBLIC_FOLDER_URL = `https://drive.google.com/drive/folders/${PUBLIC_FOLDER_ID}`
export const PUBLIC_FOLDER_EMBED = `https://drive.google.com/embeddedfolderview?id=${PUBLIC_FOLDER_ID}#list`

export function extractSheetId(raw: string): string | null {
  try {
    const url = new URL(raw.trim())
    if (url.protocol !== 'https:' || url.hostname !== 'docs.google.com') return null
    const match = url.pathname.match(/^\/spreadsheets\/d\/([A-Za-z0-9_-]{10,160})(?:\/|$)/)
    return match && SHEET_ID.test(match[1]) ? match[1] : null
  } catch { return null }
}

export function sheetUrl(id: string): string | null {
  return SHEET_ID.test(id) ? `https://docs.google.com/spreadsheets/d/${id}/edit` : null
}

export function sheetEmbedUrl(id: string): string | null {
  return SHEET_ID.test(id) ? `https://docs.google.com/spreadsheets/d/${id}/edit?rm=minimal` : null
}
