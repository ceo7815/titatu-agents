import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './lib/supabase'
import logo from './assets/titatu-logo.png'
import { AppShell } from './pages/AppShell'
import { Login } from './pages/Login'
import { Home } from './pages/Home'
import { Agents } from './pages/Agents'
import { Costs } from './pages/Costs'
import { Chats } from './pages/Chats'
import { WorkspaceProvider } from './lib/workspace'

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  if (session === undefined) {
    return (
      <div className="boot">
        <img src={logo} alt="TitaTu" className="boot-logo" />
        <p>טוען…</p>
      </div>
    )
  }

  if (!session) return <Login />

  return (
    <WorkspaceProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Home />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/costs" element={<Costs />} />
          <Route path="/chats" element={<Chats />} />
          <Route path="/activity" element={<Navigate to="/chats" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </WorkspaceProvider>
  )
}
