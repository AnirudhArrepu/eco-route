import { useEffect, useRef, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { isApiConfigured } from '../api/client'
import { signUp, confirmEmail, resendConfirmation } from '../api/auth'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import ErrorMessage from '../components/ui/ErrorMessage'

export default function AuthPage() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState('')
  const controller = useRef(null)
  const { account, signIn } = useAuth()
  const location = useLocation()
  const destination = location.state?.from || '/'
  useEffect(() => () => controller.current?.abort(), [])
  if (account) return <Navigate to={destination} state={destination.state} replace />
  const changeMode = next => { setMode(next); setError(null); setNotice(''); setPassword('') }
  const submit = async event => {
    event.preventDefault()
    if (busy) return
    setError(null); setNotice(''); setBusy(true)
    controller.current = new AbortController()
    try {
      const credentials = { email: email.trim(), password }
      if (mode === 'login') { await signIn(credentials, controller.current.signal) }
      else if (mode === 'signup') {
        if (!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^a-zA-Z0-9]).{12,256}$/.test(password)) throw new Error('Use at least 12 characters with uppercase, lowercase, a number, and a symbol.')
        const result = await signUp(credentials, controller.current.signal)
        setPassword(''); setMode(result.confirmation_required ? 'confirm' : 'login')
        setNotice(result.confirmation_required ? 'Check your email for a confirmation code.' : 'Account created. Sign in to continue.')
      } else {
        await confirmEmail({ email: email.trim(), code: code.trim() }, controller.current.signal)
        setMode('login'); setCode(''); setNotice('Email confirmed. You can now sign in.')
      }
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  const resend = async () => {
    setBusy(true); setError(null); controller.current = new AbortController()
    try { await resendConfirmation(email.trim(), controller.current.signal); setNotice('A new confirmation code has been sent.') }
    catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  return <section className="page-narrow py-12 sm:py-20">
    <p className="eyebrow">A LITTLE DIRECTION STARTS HERE</p>
    <h1 className="page-title mt-4">{mode === 'login' ? 'Welcome back.' : mode === 'signup' ? 'Make room for your day.' : 'Check your inbox.'}</h1>
    <p className="mt-3 text-neutral-500">{mode === 'confirm' ? 'Enter the code sent to your email.' : 'Sign in to plan, discover, and keep everything together.'}</p>
    {!isApiConfigured && <div className="notice mt-6">Backend connection is not configured. Set VITE_API_BASE_URL in your local environment.</div>}
    <form onSubmit={submit} className="mt-8 grid gap-5">
      <Input label="Email" type="email" autoComplete="email" required maxLength={320} value={email} onChange={e => setEmail(e.target.value)} />
      {mode !== 'confirm' ? <Input label="Password" type="password" autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required
        minLength={mode === 'signup' ? 12 : 1} maxLength={256} value={password} onChange={e => setPassword(e.target.value)}
        hint={mode === 'signup' ? '12+ characters, including uppercase, lowercase, a number, and a symbol.' : undefined} />
        : <Input label="Confirmation code" autoComplete="one-time-code" required maxLength={32} value={code} onChange={e => setCode(e.target.value)} />}
      <ErrorMessage error={error} />
      {notice && <p role="status" className="notice">{notice}</p>}
      <Button type="submit" busy={busy} disabled={!isApiConfigured}>{mode === 'login' ? 'Sign in' : mode === 'signup' ? 'Create account' : 'Confirm email'}<ArrowRight size={17} /></Button>
    </form>
    <div className="mt-5 flex flex-wrap gap-2">
      <Button variant="ghost" disabled={busy} onClick={() => changeMode(mode === 'login' ? 'signup' : 'login')}>{mode === 'login' ? 'Create an account' : 'Back to sign in'}</Button>
      {mode === 'confirm' ? <Button variant="ghost" disabled={busy || !email.trim()} onClick={resend}>Resend code</Button>
        : <Button variant="ghost" disabled={busy} onClick={() => changeMode('confirm')}>Confirm my email</Button>}
    </div>
  </section>
}
