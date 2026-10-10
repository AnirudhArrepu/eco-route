import { LoaderCircle } from 'lucide-react'

export default function LoadingState({ children = 'Loading…' }) {
  return <div role="status" className="flex items-center gap-3 py-6 text-sm text-neutral-500">
    <LoaderCircle size={18} className="loading-spin" aria-hidden="true" />{children}
  </div>
}
