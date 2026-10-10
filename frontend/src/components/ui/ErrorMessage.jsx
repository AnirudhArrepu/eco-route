import { AlertCircle } from 'lucide-react'

export default function ErrorMessage({ error }) {
  if (!error) return null
  const conflicts = error.detail?.conflicts
  return <div role="alert" className="notice flex gap-3">
    <AlertCircle size={18} className="mt-0.5 shrink-0" />
    <div className="min-w-0"><p>{typeof error === 'string' ? error : error.message || 'Something went wrong.'}</p>
      {conflicts?.length > 0 && <ul className="mt-2 list-disc pl-4">{conflicts.map((item, i) => <li key={i}>{item.reason}</li>)}</ul>}
    </div>
  </div>
}
