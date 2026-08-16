import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { ALL_AGENTS, useWorkspace } from '../lib/workspace'
import logo from '../assets/titatu-logo.png'

const LINKS = [
  { to: '/', label: 'בית', keywords: ['בית', 'סקירה', 'home'], icon: 'home' },
  { to: '/agents', label: 'סוכנים', keywords: ['סוכנים', 'חיבור', 'טלגרם'], icon: 'agents' },
  { to: '/costs', label: 'עלויות', keywords: ['עלויות', 'עלות', 'דולר'], icon: 'costs' },
  { to: '/chats', label: 'שיחות', keywords: ['שיחות', 'משתמשים', 'פעילות', 'יומן', 'הודעות'], icon: 'chats' },
] as const

function TabIcon({ name }: { name: (typeof LINKS)[number]['icon'] }) {
  const common = {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  if (name === 'home') {
    return (
      <svg {...common}>
        <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z" />
      </svg>
    )
  }
  if (name === 'agents') {
    return (
      <svg {...common}>
        <circle cx="8" cy="8" r="3" />
        <circle cx="16.5" cy="9" r="2.4" />
        <path d="M3.5 19c.6-3 2.6-4.6 4.5-4.6s3.9 1.6 4.5 4.6" />
        <path d="M13.2 19c.4-2.2 1.8-3.4 3.3-3.4 1.6 0 2.9 1.2 3.3 3.4" />
      </svg>
    )
  }
  if (name === 'costs') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8.2" />
        <path d="M12 7.2v9.6M9.2 9.4c.7-1 2-1.6 2.8-1.6 1.7 0 2.8.8 2.8 2.1 0 2.8-5.6 1.5-5.6 4.2 0 1.3 1.2 2.2 3 2.2 1 0 2-.4 2.7-1.2" />
      </svg>
    )
  }
  return (
    <svg {...common}>
      <path d="M5 18.5 6.2 15A7.5 7.5 0 1 1 12 19.5H7.2z" />
    </svg>
  )
}

function userLabel(email: string | undefined, fullName: string | undefined) {
  if (fullName) return fullName
  if (!email) return 'משתמש'
  if (email.startsWith('sahar')) return 'סהר'
  if (email.startsWith('or@')) return 'אור'
  return email.split('@')[0]
}

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])
  const date = new Intl.DateTimeFormat('he-IL', {
    timeZone: 'Asia/Jerusalem',
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(now)
  const time = new Intl.DateTimeFormat('he-IL', {
    timeZone: 'Asia/Jerusalem',
    hour: '2-digit',
    minute: '2-digit',
  }).format(now)
  return { date, time }
}

export function AppShell() {
  const { agents, selectedId, setSelectedId } = useWorkspace()
  const { date, time } = useClock()
  const navigate = useNavigate()
  const [email, setEmail] = useState<string>()
  const [fullName, setFullName] = useState<string>()
  const [open, setOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const dropRef = useRef<HTMLDivElement>(null)
  const barDropRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLDivElement>(null)
  const accountRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? undefined)
      const meta = data.user?.user_metadata as { full_name?: string } | undefined
      setFullName(meta?.full_name)
    })
  }, [])

  useEffect(() => {
    function onDoc(event: MouseEvent | TouchEvent) {
      const target = event.target as Node
      const inAgent =
        (dropRef.current && dropRef.current.contains(target)) ||
        (barDropRef.current && barDropRef.current.contains(target))
      if (!inAgent) setOpen(false)
      if (searchRef.current && !searchRef.current.contains(target)) setSearchOpen(false)
      if (accountRef.current && !accountRef.current.contains(target)) setAccountOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('touchstart', onDoc)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('touchstart', onDoc)
    }
  }, [])

  const selectedLabel =
    selectedId === ALL_AGENTS
      ? 'כל הסוכנים'
      : agents.find((agent) => agent.id === selectedId)?.display_name ?? 'סוכן'

  const hits = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    const pages = LINKS.filter(
      (link) =>
        link.label.includes(query.trim()) ||
        link.keywords.some((word) => word.includes(q) || q.includes(word)),
    ).map((link) => ({ kind: 'page' as const, id: link.to, label: link.to === '/chats' ? 'שיחות ומשתמשים' : link.label, hint: 'מסך' }))
    const people = agents
      .filter((agent) => agent.display_name.includes(query.trim()) || agent.role_label.includes(query.trim()))
      .map((agent) => ({
        kind: 'agent' as const,
        id: agent.id,
        label: agent.display_name,
        hint: agent.role_label,
      }))
    const all =
      'כל הסוכנים'.includes(query.trim()) || q === 'הכל' || q === 'all'
        ? [{ kind: 'agent' as const, id: ALL_AGENTS, label: 'כל הסוכנים', hint: 'תצוגה מלאה' }]
        : []
    return [...all, ...people, ...pages].slice(0, 8)
  }, [query, agents])

  function pick(hit: { kind: 'page' | 'agent'; id: string }) {
    if (hit.kind === 'page') navigate(hit.id)
    else {
      setSelectedId(hit.id)
      if (hit.id !== ALL_AGENTS) navigate('/agents')
    }
    setQuery('')
    setSearchOpen(false)
  }

  function AgentPicker({ boxRef }: { boxRef: typeof dropRef }) {
    return (
      <div className="agent-drop" ref={boxRef}>
        <span className="drop-label">סוכן</span>
        <button
          type="button"
          className="drop-btn"
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span>{selectedLabel}</span>
          <em aria-hidden="true">▾</em>
        </button>
        {open ? (
          <ul className="drop-menu" role="listbox">
            <li>
              <button
                type="button"
                className={selectedId === ALL_AGENTS ? 'on' : undefined}
                onClick={() => {
                  setSelectedId(ALL_AGENTS)
                  setOpen(false)
                }}
              >
                כל הסוכנים
              </button>
            </li>
            {agents.map((agent) => (
              <li key={agent.id}>
                <button
                  type="button"
                  className={selectedId === agent.id ? 'on' : undefined}
                  onClick={() => {
                    setSelectedId(agent.id)
                    setOpen(false)
                  }}
                >
                  <i className={agent.process_alive ? 'dot live' : 'dot'} />
                  {agent.display_name}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    )
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <img src={logo} alt="TitaTu" className="shell-logo" />
          <p>מערכת סוכני AI</p>
        </div>

        <AgentPicker boxRef={dropRef} />

        <nav className="side-nav" aria-label="קטגוריות">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              className={({ isActive }) => (isActive ? 'active' : undefined)}
            >
              {link.to === '/chats' ? 'שיחות ומשתמשים' : link.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-user">
          <strong>{userLabel(email, fullName)}</strong>
          <span>{email}</span>
          <button type="button" className="logout" onClick={() => void supabase.auth.signOut()}>
            התנתק
          </button>
        </div>
      </aside>

      <div className="workspace">
        <header className="workspace-bar">
          <img src={logo} alt="TitaTu" className="bar-logo" />
          <AgentPicker boxRef={barDropRef} />
          <div className="smart-search" ref={searchRef}>
            <input
              type="search"
              placeholder="חיפוש סוכן, מסך או עלות…"
              enterKeyHint="search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setSearchOpen(true)
              }}
              onFocus={() => setSearchOpen(true)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && hits[0]) pick(hits[0])
              }}
            />
            {searchOpen && query.trim() ? (
              <ul className="search-hits">
                {hits.length ? (
                  hits.map((hit) => (
                    <li key={`${hit.kind}-${hit.id}`}>
                      <button type="button" onClick={() => pick(hit)}>
                        <strong>{hit.label}</strong>
                        <span>{hit.hint}</span>
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="empty">אין תוצאות</li>
                )}
              </ul>
            ) : null}
          </div>
          <div className="clock">
            <strong>{time}</strong>
            <span>{date}</span>
          </div>
          <div className="bar-account" ref={accountRef}>
            <button
              type="button"
              className="account-btn"
              aria-expanded={accountOpen}
              onClick={() => setAccountOpen((v) => !v)}
            >
              {userLabel(email, fullName)}
            </button>
            {accountOpen ? (
              <div className="account-sheet">
                <strong>{userLabel(email, fullName)}</strong>
                <span>{email}</span>
                <button type="button" className="logout" onClick={() => void supabase.auth.signOut()}>
                  התנתק
                </button>
              </div>
            ) : null}
          </div>
        </header>
        <main className="page">
          <Outlet />
        </main>
      </div>

      <nav className="tab-bar" aria-label="ניווט ראשי">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
            className={({ isActive }) => (isActive ? 'active' : undefined)}
          >
            <TabIcon name={link.icon} />
            <span>{link.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
