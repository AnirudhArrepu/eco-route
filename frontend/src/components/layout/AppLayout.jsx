import { Outlet } from 'react-router-dom'
import Header from './Header'

export default function AppLayout() {
  return <div className="app-shell min-h-dvh bg-white text-neutral-900">
    <a href="#main-content" className="skip-link">Skip to content</a>
    <Header /><main id="main-content" className="app-main" tabIndex={-1}><Outlet /></main>
  </div>
}
