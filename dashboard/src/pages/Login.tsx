import { useState, type FormEvent } from 'react'
import { supabase } from '../lib/supabase'
import logo from '../assets/titatu-logo.png'
import { TechBackdrop } from './TechBackdrop'

export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const { error: next } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    })
    setBusy(false)
    if (next) setError('אימייל או סיסמה לא נכונים')
  }

  return (
    <main className="login">
      <TechBackdrop />
      <div className="login-scan" aria-hidden="true" />
      <div className="login-center">
        <img className="login-logo" src={logo} alt="TitaTu" />
        <section className="login-stage">
          <h1 className="login-title">
            מערכת סוכני <span>AI</span>
          </h1>
          <form className="login-form" onSubmit={onSubmit}>
            <label>
              אימייל
              <input
                type="email"
                inputMode="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label>
              סיסמה
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            {error ? <p className="form-error">{error}</p> : null}
            <button type="submit" disabled={busy}>
              {busy ? 'נכנס…' : 'כניסה'}
            </button>
          </form>
        </section>
      </div>
    </main>
  )
}
