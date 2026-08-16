import { useEffect, useMemo, useState } from 'react'
import { agentAlert, loadActivity, loadUsage90d, sumMonth, sumToday } from '../lib/data'
import { formatUsd, relativeHe, todayJerusalem, toJerusalemDay } from '../lib/format'
import { ALL_AGENTS, useWorkspace } from '../lib/workspace'
import type { ActivityEvent, UsageEvent } from '../lib/types'

export function Home() {
  const { scopedAgents, selectedId, loading } = useWorkspace()
  const [usage, setUsage] = useState<UsageEvent[]>([])
  const [activity, setActivity] = useState<ActivityEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([loadUsage90d(), loadActivity()])
      .then(([nextUsage, nextActivity]) => {
        setUsage(nextUsage)
        setActivity(nextActivity)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  const scopedUsage = useMemo(
    () =>
      selectedId === ALL_AGENTS
        ? usage
        : usage.filter((event) => event.agent_id === selectedId),
    [usage, selectedId],
  )
  const scopedActivity = useMemo(
    () =>
      selectedId === ALL_AGENTS
        ? activity
        : activity.filter((event) => event.agent_id === selectedId),
    [activity, selectedId],
  )

  const running = scopedAgents.filter((a) => a.is_live && a.process_alive).length
  const down = scopedAgents.filter((a) => a.is_live && !a.process_alive).length
  const waiting = scopedAgents.filter((a) => !a.is_live).length
  const brokenLinks = scopedAgents.flatMap((agent) =>
    agent.connections.filter((c) => !c.connected),
  ).length
  const today = todayJerusalem()
  const messagesToday = scopedActivity.filter(
    (event) => toJerusalemDay(event.created_at) === today,
  ).length
  const lastTelegram = scopedAgents
    .map((agent) => agent.last_telegram_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1)
  const alerts = scopedAgents
    .map(agentAlert)
    .filter((text): text is string => Boolean(text))

  if (error) return <p className="form-error">{error}</p>
  if (loading) return <p className="muted">טוען…</p>

  return (
    <div className="home">
      <header className="page-head home-head">
        <h2>סקירה</h2>
        <p>מצב המערכת עכשיו</p>
      </header>

      {alerts.map((text) => (
        <div key={text} className="banner-alert" role="alert">
          {text}
        </div>
      ))}

      <section className="board home-cubes" aria-label="מצב סוכנים">
        <article>
          <p>סה״כ</p>
          <strong>{scopedAgents.length}</strong>
        </article>
        <article>
          <p>פעילים</p>
          <strong className="ok">{running}</strong>
        </article>
        <article>
          <p>לא פועלים</p>
          <strong className={down ? 'down' : undefined}>{down}</strong>
        </article>
        <article>
          <p>בהקמה</p>
          <strong>{waiting}</strong>
        </article>
        <article>
          <p>חיבורים תקולים</p>
          <strong className={brokenLinks ? 'down' : undefined}>{brokenLinks}</strong>
        </article>
      </section>

      <section className="board home-cubes" aria-label="עלויות ופעילות">
        <article>
          <p>עלות היום</p>
          <strong>{formatUsd(sumToday(scopedUsage))}</strong>
        </article>
        <article>
          <p>עלות החודש</p>
          <strong>{formatUsd(sumMonth(scopedUsage))}</strong>
        </article>
        <article>
          <p>הודעות היום</p>
          <strong>{messagesToday}</strong>
        </article>
        <article>
          <p>פעילות אחרונה</p>
          <strong className="board-soft">{relativeHe(lastTelegram ?? null)}</strong>
        </article>
      </section>
    </div>
  )
}
