import { ModalBackdrop } from './AppDialog'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

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
  const [fitSize, setFitSize] = useState<{
    width: number; height: number; viewportWidth: number; viewportHeight: number
  } | null>(null)
  const canvasRef = useRef<HTMLDivElement>(null)
  const imageRef = useRef<HTMLImageElement>(null)
  const zoomRef = useRef(1)
  const zoomAnchor = useRef<{ x: number; y: number; clientX: number; clientY: number } | null>(null)
  const [panning, setPanning] = useState(false)
  const pan = useRef<{
    canvas: HTMLDivElement; pointerId: number; x: number; y: number; left: number; top: number
  } | null>(null)
  const dialogRef = useRef<HTMLElement>(null)
  const activeIndex = images.findIndex(image => image.id === activeId)
  const current = activeIndex >= 0 ? images[activeIndex] : null

  const endPan = useCallback(() => {
    const drag = pan.current
    if (!drag) return
    pan.current = null
    setPanning(false)
    if (drag.canvas.hasPointerCapture?.(drag.pointerId)) drag.canvas.releasePointerCapture(drag.pointerId)
  }, [])

  useEffect(() => {
    window.addEventListener('blur', endPan)
    return () => window.removeEventListener('blur', endPan)
  }, [endPan])

  const measureImage = useCallback(() => {
    const canvas = canvasRef.current
    const image = imageRef.current
    if (!canvas || !image?.naturalWidth || !image.naturalHeight) return
    const bounds = canvas.getBoundingClientRect()
    if (!bounds.width || !bounds.height) return
    const scale = Math.min(1, bounds.width / image.naturalWidth, bounds.height / image.naturalHeight)
    const width = image.naturalWidth * scale
    const height = image.naturalHeight * scale
    setFitSize(previous => previous?.width === width && previous.height === height
      && previous.viewportWidth === bounds.width && previous.viewportHeight === bounds.height
      ? previous : { width, height, viewportWidth: bounds.width, viewportHeight: bounds.height })
  }, [])

  useLayoutEffect(() => {
    endPan()
    setZoom(1)
    zoomRef.current = 1
    zoomAnchor.current = null
    setFitSize(null)
    setLoadFailed(false)
    if (canvasRef.current) {
      canvasRef.current.scrollTop = 0
      canvasRef.current.scrollLeft = 0
    }
    measureImage()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measureImage)
    if (canvasRef.current) observer?.observe(canvasRef.current)
    window.addEventListener('resize', measureImage)
    return () => { endPan(); observer?.disconnect(); window.removeEventListener('resize', measureImage) }
  }, [activeId, current?.src, measureImage, endPan])

  const changeZoom = useCallback((value: number, clientX?: number, clientY?: number) => {
    const canvas = canvasRef.current
    const image = imageRef.current
    if (!canvas || !image) return
    const bounds = image.getBoundingClientRect()
    if (!bounds.width || !bounds.height) return
    const next = Math.max(0.5, Math.min(4, value))
    if (next === zoomRef.current) return
    endPan()
    const viewport = canvas.getBoundingClientRect()
    const x = clientX ?? viewport.left + canvas.clientWidth / 2
    const y = clientY ?? viewport.top + canvas.clientHeight / 2
    zoomAnchor.current = {
      x: Math.max(0, Math.min(1, (x - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (y - bounds.top) / bounds.height)),
      clientX: x, clientY: y,
    }
    zoomRef.current = next
    setZoom(next)
  }, [endPan])

  useLayoutEffect(() => {
    const anchor = zoomAnchor.current
    const canvas = canvasRef.current
    const image = imageRef.current
    if (!anchor || !canvas || !image) return
    const bounds = image.getBoundingClientRect()
    canvas.scrollLeft += bounds.left + bounds.width * anchor.x - anchor.clientX
    canvas.scrollTop += bounds.top + bounds.height * anchor.y - anchor.clientY
    zoomAnchor.current = null
  }, [zoom])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !fitSize || loadFailed) return
    const onWheel = (event: WheelEvent) => {
      if (!event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return
      event.preventDefault()
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.clientHeight : 1
      const delta = Math.max(-400, Math.min(400, event.deltaY * unit))
      changeZoom(zoomRef.current * Math.exp(-delta * 0.002), event.clientX, event.clientY)
    }
    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [activeId, fitSize, loadFailed, changeZoom])

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
              disabled={!fitSize || loadFailed}
              onChange={event => changeZoom(Number(event.target.value))}
              aria-label="圖片縮放" />
            <span>{Math.round(zoom * 100)}%</span>
          </label>
          <button type="button" className="inspector-lightbox-close" data-dialog-cancel
            onClick={onClose} aria-label="關閉預覽">關閉</button>
        </div>
        <div className={`inspector-lightbox-canvas${zoom > 1 && !loadFailed ? ' can-pan' : ''}${panning ? ' is-panning' : ''}`}
          ref={canvasRef}
          onPointerDown={event => {
            const canvas = event.currentTarget
            if (event.pointerType !== 'mouse' || event.button !== 0 || !fitSize || loadFailed || zoomRef.current <= 1
              || (canvas.scrollWidth <= canvas.clientWidth && canvas.scrollHeight <= canvas.clientHeight)) return
            const bounds = canvas.getBoundingClientRect()
            // Leave the native scrollbars available to drag normally.
            if (event.clientX >= bounds.left + canvas.clientLeft + canvas.clientWidth
              || event.clientY >= bounds.top + canvas.clientTop + canvas.clientHeight) return
            event.preventDefault()
            canvas.setPointerCapture?.(event.pointerId)
            pan.current = { canvas, pointerId: event.pointerId, x: event.clientX, y: event.clientY,
              left: canvas.scrollLeft, top: canvas.scrollTop }
            setPanning(true)
          }}
          onPointerMove={event => {
            const drag = pan.current
            if (!drag || drag.pointerId !== event.pointerId) return
            if ((event.buttons & 1) === 0) { endPan(); return }
            event.preventDefault()
            drag.canvas.scrollLeft = drag.left - (event.clientX - drag.x)
            drag.canvas.scrollTop = drag.top - (event.clientY - drag.y)
          }}
          onPointerUp={endPan} onPointerCancel={endPan} onLostPointerCapture={endPan}>
          {loadFailed
            ? <p role="alert">這張照片目前無法讀取，請確認來源磁碟與雲端同步狀態。</p>
            : <div className="inspector-lightbox-stage" style={fitSize ? {
                width: fitSize.viewportWidth * Math.max(1, zoom),
                height: fitSize.viewportHeight * Math.max(1, zoom),
              } : { width: '100%', height: '100%' }}>
                <img key={current.id} ref={imageRef} src={current.src} alt={current.filename} draggable={false}
                  style={fitSize ? { width: fitSize.width * zoom, height: fitSize.height * zoom } : {
                    maxWidth: '100%', maxHeight: '100%',
                  }} onLoad={measureImage} onError={() => { endPan(); setLoadFailed(true) }} />
              </div>}
        </div>
        <footer className="inspector-lightbox-footer">
          <strong>{current.subtitle}</strong>
          <span title={current.path}>{current.path}</span>
          <small>按住左鍵拖曳平移 · 滾輪以滑鼠位置放大／縮小 · 方向鍵 ← → 切換照片 · Esc 關閉</small>
        </footer>
      </section>
    </ModalBackdrop>
  )
}
