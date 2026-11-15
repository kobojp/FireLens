import { ModalBackdrop } from './AppDialog'
import { useEffect, useRef, useState } from 'react'

export type InspectorImage = {
  id: number
  filename: string
  title: string
  subtitle: string
  path: string
  src: string
}

export function adjacentImage(
  images: InspectorImage[], activeId: number, direction: -1 | 1,
): number | null {
  const position = images.findIndex(image => image.id === activeId)
  const next = position + direction
  return position < 0 || next < 0 || next >= images.length ? null : images[next].id
}

/** The same large dark image-viewing interaction used in the photo wall. */
export function InspectorImageViewer({
  images, activeId, onSelect, onClose, label = '照片品質檢查大圖預覽',
}: {
  images: InspectorImage[]
  activeId: number | null
  onSelect: (id: number) => void
  label?: string
  onClose: () => void
}) {
  const [zoom, setZoom] = useState(1)
  const [loadFailed, setLoadFailed] = useState(false)
  const canvasRef = useRef<HTMLDivElement>(null)
  const dialogRef = useRef<HTMLElement>(null)
  const activeIndex = images.findIndex(image => image.id === activeId)
  const current = activeIndex >= 0 ? images[activeIndex] : null

  useEffect(() => {
    setZoom(1)
    setLoadFailed(false)
    if (canvasRef.current) {
      canvasRef.current.scrollTop = 0
      canvasRef.current.scrollLeft = 0
    }
  }, [activeId])

  useEffect(() => {
    if (activeId === null || !current) return
    const onKeyDown = (event: KeyboardEvent) => {
      const element = event.target instanceof Element ? event.target : null
      if (element?.closest('input, textarea, select')) return
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        const candidate = adjacentImage(images, current.id, event.key === 'ArrowLeft' ? -1 : 1)
        if (candidate !== null) {
          event.preventDefault()
          onSelect(candidate)
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [activeId, current, images, onClose, onSelect])

  if (!current) return null

  const previous = adjacentImage(images, current.id, -1)
  const next = adjacentImage(images, current.id, 1)

  return (
    <ModalBackdrop onCancel={onClose} className="preview-backdrop inspector-lightbox-backdrop" role="presentation"
      onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
      <section className="inspector-lightbox" role="dialog" aria-modal="true"
        ref={dialogRef} aria-label={label} tabIndex={-1}>
        <div className="inspector-lightbox-toolbar">
          <b className="inspector-lightbox-title" title={current.title}>{current.title}</b>
          <div className="inspector-lightbox-navigation" role="group" aria-label="照片切換">
            <button type="button" disabled={previous === null} aria-label="上一張照片"
              onClick={() => { if (previous !== null) onSelect(previous) }}>← 上一張</button>
            <span aria-live="polite">{activeIndex + 1}／{images.length}</span>
            <button type="button" disabled={next === null} aria-label="下一張照片"
              onClick={() => { if (next !== null) onSelect(next) }}>下一張 →</button>
          </div>
          <label className="inspector-lightbox-zoom">縮放
            <input type="range" min="0.5" max="4" step="0.1" value={zoom}
              onChange={event => setZoom(Number(event.target.value))}
              aria-label="圖片縮放" />
            <span>{Math.round(zoom * 100)}%</span>
          </label>
          <button type="button" className="inspector-lightbox-close" data-dialog-cancel
            onClick={onClose} aria-label="關閉預覽">關閉</button>
        </div>
        <div className="inspector-lightbox-canvas" ref={canvasRef}>
          {loadFailed
            ? <p role="alert">這張照片目前無法讀取，請確認來源磁碟與雲端同步狀態。</p>
            : <img key={current.id} src={current.src} alt={current.filename}
                style={{
                  width: zoom === 1 ? 'auto' : `${zoom * 100}%`,
                  maxWidth: zoom === 1 ? '100%' : 'none',
                  maxHeight: zoom === 1 ? '100%' : 'none',
                }} onError={() => setLoadFailed(true)} />}
        </div>
        <footer className="inspector-lightbox-footer">
          <strong>{current.subtitle}</strong>
          <span title={current.path}>{current.path}</span>
          <small>方向鍵 ← → 切換照片 · Esc 關閉 · 縮放後可捲動檢查標籤細節</small>
        </footer>
      </section>
    </ModalBackdrop>
  )
}
