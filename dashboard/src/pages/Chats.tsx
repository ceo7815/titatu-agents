import { useEffect, useMemo, useRef, useState } from 'react'
import { loadChatMessages, loadChatUsers } from '../lib/data'
import { formatTimeHe } from '../lib/format'
import { ALL_AGENTS, useWorkspace } from '../lib/workspace'
import type { ChatMessage, ChatUser } from '../lib/types'

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0] ?? ''}${parts[parts.length - 1][0] ?? ''}`.toUpperCase()
}

function previewText(value: string) {
  const text = value.trim()
  if (!text || text === '-' || text === '—' || text === '–') return 'אין הודעות'
  return text
}

function useNarrow() {
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 860px)').matches,
  )
  useEffect(() => {
    const media = window.matchMedia('(max-width: 860px)')
    const sync = () => setNarrow(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])
  return narrow
}

export function Chats() {
  const { selectedId, loading } = useWorkspace()
  const narrow = useNarrow()
  const [users, setUsers] = useState<ChatUser[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [threadOpen, setThreadOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const threadRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    const refresh = () =>
      loadChatUsers()
        .then((rows) => {
          if (!alive) return
          setUsers(rows)
          setActiveId((current) => {
            if (current) return current
            return narrow ? null : rows[0]?.id ?? null
          })
        })
        .catch((err: Error) => {
          if (alive) setError(err.message)
        })
    refresh()
    const id = window.setInterval(refresh, 12000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [narrow])

  const scopedUsers = useMemo(
    () =>
      selectedId === ALL_AGENTS
        ? users
        : users.filter((user) => user.agent_id === selectedId),
    [users, selectedId],
  )

  useEffect(() => {
    if (activeId && !scopedUsers.some((user) => user.id === activeId)) {
      setActiveId(narrow ? null : scopedUsers[0]?.id ?? null)
      if (narrow) setThreadOpen(false)
    }
  }, [activeId, scopedUsers, narrow])

  useEffect(() => {
    if (!activeId) {
      setMessages([])
      return
    }
    let alive = true
    const refresh = () =>
      loadChatMessages(activeId)
        .then((rows) => {
          if (alive) setMessages(rows)
        })
        .catch((err: Error) => {
          if (alive) setError(err.message)
        })
    refresh()
    const id = window.setInterval(refresh, 8000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [activeId])

  useEffect(() => {
    const node = threadRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, threadOpen])

  useEffect(() => {
    document.body.classList.toggle('chat-open', narrow && threadOpen)
    return () => document.body.classList.remove('chat-open')
  }, [narrow, threadOpen])

  const active = scopedUsers.find((user) => user.id === activeId) ?? null
  const showThread = !narrow || threadOpen

  if (error) return <p className="form-error">{error}</p>
  if (loading) return <p className="muted">טוען…</p>

  return (
    <div className="chats-page">
      <header className="page-head">
        <h2>שיחות ומשתמשים</h2>
        <p>היסטוריה מלאה לפי משתמש טלגרם</p>
      </header>

      <section className={showThread && narrow ? 'chats thread-open' : 'chats'}>
        <aside className="chat-users" aria-label="משתמשים">
          {scopedUsers.length === 0 ? (
            <p className="muted chat-empty">אין משתמשים עדיין.</p>
          ) : (
            <ul>
              {scopedUsers.map((user) => (
                <li key={user.id}>
                  <button
                    type="button"
                    className={user.id === activeId && showThread ? 'on' : undefined}
                    onClick={() => {
                      setActiveId(user.id)
                      setThreadOpen(true)
                    }}
                  >
                    <span className="chat-avatar" aria-hidden="true">
                      {initials(user.display_name)}
                    </span>
                    <span className="chat-user-body">
                      <span className="chat-user-top">
                        <strong>{user.display_name}</strong>
                        <em>{user.last_message_at ? formatTimeHe(user.last_message_at) : ''}</em>
                      </span>
                      <span className="chat-user-preview">{previewText(user.last_preview)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="chat-thread">
          {active && showThread ? (
            <>
              <header>
                {narrow ? (
                  <button type="button" className="chat-back" onClick={() => setThreadOpen(false)}>
                    חזרה
                  </button>
                ) : null}
                <h3>{active.display_name}</h3>
                <p>טלגרם · {messages.length} הודעות</p>
              </header>
              <div className="chat-log" ref={threadRef}>
                {messages.length === 0 ? (
                  <p className="muted chat-empty">אין הודעות למשתמש הזה עדיין.</p>
                ) : (
                  messages.map((row) => (
                    <article
                      key={row.id}
                      className={row.direction === 'in' ? 'bubble-row in' : 'bubble-row out'}
                    >
                      <div className={row.direction === 'in' ? 'bubble in' : 'bubble out'}>
                        <p>{row.body || '—'}</p>
                        <time>{formatTimeHe(row.created_at)}</time>
                      </div>
                    </article>
                  ))
                )}
              </div>
            </>
          ) : (
            <p className="muted chat-empty">בחרו משתמש כדי לראות את השיחה.</p>
          )}
        </div>
      </section>
    </div>
  )
}
