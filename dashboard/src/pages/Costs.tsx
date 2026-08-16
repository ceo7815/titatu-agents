import { useEffect, useMemo, useState } from 'react'
import {
  GPT41_MINI,
  last90Days,
  loadUsage90d,
  rollupDaily,
  rollupMonthly,
  sumMonth,
  sumToday,
  tokenTotals,
} from '../lib/data'
import { formatDayHe, formatMonthHe, formatTokens, formatUsd, todayJerusalem, toJerusalemDay } from '../lib/format'
import { ALL_AGENTS, useWorkspace } from '../lib/workspace'
import type { UsageEvent } from '../lib/types'

export function Costs() {
  const { selectedId, loading } = useWorkspace()
  const [usage, setUsage] = useState<UsageEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const refresh = () =>
      loadUsage90d()
        .then((rows) => {
          if (alive) setUsage(rows)
        })
        .catch((err: Error) => {
          if (alive) setError(err.message)
        })
    refresh()
    const id = window.setInterval(refresh, 20000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [])

  const scopedUsage = useMemo(
    () =>
      selectedId === ALL_AGENTS
        ? usage
        : usage.filter((event) => event.agent_id === selectedId),
    [usage, selectedId],
  )
  const daily = useMemo(() => rollupDaily(scopedUsage), [scopedUsage])
  const monthly = useMemo(() => rollupMonthly(scopedUsage), [scopedUsage])
  const todayRows = useMemo(() => {
    const today = todayJerusalem()
    return scopedUsage.filter((event) => toJerusalemDay(event.created_at) === today)
  }, [scopedUsage])
  const todayTokens = tokenTotals(todayRows)
  const allTokens = tokenTotals(scopedUsage)
  const days = last90Days()
  const byDay = new Map(daily.map((row) => [row.day, row.cost_usd]))
  const max = Math.max(...days.map((day) => byDay.get(day) ?? 0), 0.01)

  if (error) return <p className="form-error">{error}</p>
  if (loading) return <p className="muted">טוען…</p>

  return (
    <div className="costs-page">
      <header className="page-head">
        <h2>עלויות</h2>
        <p>דולר לפי טוקנים של gpt-4.1-mini — הספירה מתחילה מהרגע הזה</p>
      </header>

      <section className="cost-cubes" aria-label="סיכום עלויות">
        <article className="cost-cube">
          <p>היום</p>
          <strong>{formatUsd(sumToday(scopedUsage))}</strong>
        </article>
        <article className="cost-cube">
          <p>החודש</p>
          <strong>{formatUsd(sumMonth(scopedUsage))}</strong>
        </article>
        <article className="cost-cube">
          <p>90 יום</p>
          <strong>{formatUsd(allTokens.cost)}</strong>
        </article>
        <article className="cost-cube">
          <p>קלט היום</p>
          <strong>{formatTokens(todayTokens.prompt)}</strong>
        </article>
        <article className="cost-cube">
          <p>פלט היום</p>
          <strong>{formatTokens(todayTokens.completion)}</strong>
        </article>
        <article className="cost-cube">
          <p>קריאות מודל היום</p>
          <strong>{formatTokens(todayTokens.calls)}</strong>
        </article>
        <article className="cost-cube cost-rate">
          <p>מחיר המודל</p>
          <strong>gpt-4.1-mini</strong>
          <ul>
            <li>
              <span>קלט</span>
              <em>${GPT41_MINI.inputPerMillion.toFixed(2)} / 1M</em>
            </li>
            <li>
              <span>פלט</span>
              <em>${GPT41_MINI.outputPerMillion.toFixed(2)} / 1M</em>
            </li>
            <li>
              <span>מטמון</span>
              <em>${GPT41_MINI.cachedPerMillion.toFixed(2)} / 1M</em>
            </li>
          </ul>
        </article>
      </section>

      <section className="panel cost-panel">
        <h3>יומי — 90 יום</h3>
        <div className="bars" aria-hidden="true">
          {days.map((day) => {
            const value = byDay.get(day) ?? 0
            return (
              <div
                key={day}
                className="bar"
                title={`${day}: ${formatUsd(value)}`}
                style={{ height: `${Math.max(4, (value / max) * 100)}%` }}
              />
            )
          })}
        </div>
        {daily.length === 0 ? (
          <p className="muted">אין עדיין קריאות מודל. אחרי הודעה שעוברת במוח — יופיעו טוקנים ומחיר.</p>
        ) : (
          <div className="table-wrap stack-table">
            <table>
              <thead>
                <tr>
                  <th>יום</th>
                  <th>קלט</th>
                  <th>פלט</th>
                  <th>מטמון</th>
                  <th>קריאות</th>
                  <th>עלות</th>
                </tr>
              </thead>
              <tbody>
                {[...daily].reverse().slice(0, 31).map((row) => (
                  <tr key={row.day}>
                    <td data-label="יום">{formatDayHe(row.day)}</td>
                    <td data-label="קלט">{formatTokens(row.prompt_tokens)}</td>
                    <td data-label="פלט">{formatTokens(row.completion_tokens)}</td>
                    <td data-label="מטמון">{formatTokens(row.cache_read_tokens)}</td>
                    <td data-label="קריאות">{formatTokens(row.calls)}</td>
                    <td data-label="עלות">{formatUsd(row.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel cost-panel">
        <h3>חודשי</h3>
        {monthly.length === 0 ? (
          <p className="muted">אין נתונים חודשיים עדיין.</p>
        ) : (
          <div className="table-wrap stack-table">
            <table>
              <thead>
                <tr>
                  <th>חודש</th>
                  <th>קלט</th>
                  <th>פלט</th>
                  <th>מטמון</th>
                  <th>קריאות</th>
                  <th>עלות</th>
                </tr>
              </thead>
              <tbody>
                {monthly.map((row) => (
                  <tr key={row.month}>
                    <td data-label="חודש">{formatMonthHe(row.month)}</td>
                    <td data-label="קלט">{formatTokens(row.prompt_tokens)}</td>
                    <td data-label="פלט">{formatTokens(row.completion_tokens)}</td>
                    <td data-label="מטמון">{formatTokens(row.cache_read_tokens)}</td>
                    <td data-label="קריאות">{formatTokens(row.calls)}</td>
                    <td data-label="עלות">{formatUsd(row.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
