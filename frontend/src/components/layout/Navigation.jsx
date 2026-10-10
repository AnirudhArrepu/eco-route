import { NavLink } from 'react-router-dom'
import { ArrowUpRight, CalendarDays, House, Settings2 } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

export default function Navigation({ onNavigate }) {
  const { account } = useAuth()
  return <nav aria-label="Main navigation" className="grid gap-2">
    {[[House, '/', 'Home'], [CalendarDays, '/itinerary', 'My itinerary'], [Settings2, '/settings', 'Settings']].map(([Icon, path, title]) =>
      <NavLink key={path} to={path} onClick={onNavigate} className={({ isActive }) => `nav-link ${isActive ? 'bg-neutral-100' : ''}`}>
        <Icon size={18} /><span className="flex-1">{title}</span><ArrowUpRight size={15} />
      </NavLink>)}
    {!account && <NavLink to="/auth" className="nav-link" onClick={onNavigate}>Sign in <ArrowUpRight size={15} /></NavLink>}
  </nav>
}
