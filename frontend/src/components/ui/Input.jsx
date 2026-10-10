import { useId } from 'react'

export default function Input({ label, hint, className = '', id: suppliedId, ...props }) {
  const generatedId = useId()
  const id = suppliedId || generatedId
  return <div className={`field ${className}`}>
    {label && <label htmlFor={id}>{label}</label>}
    <input id={id} aria-describedby={hint ? `${id}-hint` : undefined} {...props} />
    {hint && <p id={`${id}-hint`} className="text-xs text-neutral-500">{hint}</p>}
  </div>
}
