import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { PlanProvider } from './context/PlanContext'
import AppLayout from './components/layout/AppLayout'
import AuthPage from './pages/AuthPage'
import HomePage from './pages/HomePage'
import PlannerPage from './pages/PlannerPage'
import ItineraryPage from './pages/ItineraryPage'
import DiscoverPage from './pages/DiscoverPage'
import SettingsPage from './pages/SettingsPage'

function Protected({ children }) {
  const { account } = useAuth()
  const location = useLocation()
  return account ? children : <Navigate to="/auth" state={{ from: location }} replace />
}
function Screens() {
  const { account } = useAuth()
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
    document.getElementById('main-content')?.focus({ preventScroll: true })
  }, [pathname])
  return <PlanProvider owner={account?.user_id}>
    <Routes><Route element={<AppLayout />}>
      <Route index element={<HomePage />} />
      <Route path="auth" element={<AuthPage />} />
      <Route path="plan" element={<Protected><PlannerPage /></Protected>} />
      <Route path="discover" element={<Protected><DiscoverPage /></Protected>} />
      <Route path="itinerary" element={<Protected><ItineraryPage /></Protected>} />
      <Route path="settings" element={<Protected><SettingsPage /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route></Routes>
  </PlanProvider>
}
export default function App() {
  return <BrowserRouter><AuthProvider><Screens /></AuthProvider></BrowserRouter>
}
