import { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import Button from './Button'

let openDialogs = 0
let previousOverflow = ''

export default function Modal({ open, onClose, title, children, className = '' }) {
  const ref = useRef(null)
  const titleId = useId()
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const dialog = ref.current
    if (!open || !dialog) return
    const previous = document.activeElement
    if (openDialogs === 0) previousOverflow = document.body.style.overflow
    openDialogs += 1
    document.body.style.overflow = 'hidden'
    dialog.showModal()
    return () => {
      dialog.close(); openDialogs = Math.max(0, openDialogs - 1)
      if (openDialogs === 0) document.body.style.overflow = previousOverflow
      if (previous?.isConnected) previous.focus?.()
    }
  }, [open])
  if (!open) return null
  return <dialog ref={ref} aria-labelledby={titleId} className={`modal ${className}`}
    onCancel={event => { event.preventDefault(); closeRef.current() }}>
    <div className="modal-header"><h2 id={titleId} className="text-lg font-semibold">{title}</h2>
      <Button variant="ghost" className="icon-button" aria-label={`Close ${title}`} onClick={onClose}><X size={20} /></Button>
    </div>
    <div className="modal-body">{children}</div>
  </dialog>
}
