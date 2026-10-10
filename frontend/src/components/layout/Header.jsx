import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowUpRight, Route, SlidersHorizontal } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import Navigation from './Navigation'

export default function Header() {
  const [open, setOpen] = useState(false)
  const { account } = useAuth()
  const location = useLocation()
  return <header className="app-header">
    <Link to="/" className="brand" aria-label="EcoRoute home"><span className="brand-mark"><Route size={21} strokeWidth={1.8} /></span>EcoRoute<span className="brand-dot" /></Link>
    <div className="flex items-center gap-2 sm:gap-5">
      <span className="hidden text-xs text-neutral-400 md:block">A thoughtful way to get there.</span>
      {!account && location.pathname !== '/auth' && <Link to="/auth" className="text-sm font-medium hover:underline">Sign in <ArrowUpRight size={14} className="inline" /></Link>}
      <Button variant="secondary" className="icon-button" aria-label="Open navigation and settings" onClick={() => setOpen(true)}><SlidersHorizontal size={18} /></Button>
    </div>
    <Modal open={open} onClose={() => setOpen(false)} title="Your space"><Navigation onNavigate={() => setOpen(false)} /></Modal>
  </header>
}
