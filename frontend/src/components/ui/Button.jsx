import { LoaderCircle } from 'lucide-react'

export default function Button({ children, variant = 'primary', busy = false, className = '', type = 'button', disabled, ...props }) {
  return <button type={type} disabled={disabled || busy} aria-busy={busy || undefined}
    className={`button ${variant === 'primary' ? 'button-primary' : variant === 'ghost' ? 'button-ghost' : 'button-secondary'} ${className}`} {...props}>
    {busy && <LoaderCircle size={17} className="loading-spin" aria-hidden="true" />}{children}
  </button>
}
