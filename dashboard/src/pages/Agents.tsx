import { agentAlert, connectionLabel } from '../lib/data'
import { relativeHe } from '../lib/format'
import { ALL_AGENTS, useWorkspace } from '../lib/workspace'
import type { ConnectionKind } from '../lib/types'

const KINDS: ConnectionKind[] = ['telegram', 'wordpress', 'openai']

export function Agents() {
  const { scopedAgents, selectedId, loading } = useWorkspace()

  if (loading) return <p className="muted">טוען…</p>

  return (
    <div className="agents-page">
      <header className="page-head">
        <h2>סוכנים</h2>
        <p>
          {selectedId === ALL_AGENTS
            ? 'כל הסוכנים במערכת'
            : `פרטי ${scopedAgents[0]?.display_name ?? 'הסוכן'}`}
        </p>
      </header>

      <section className="agent-cubes">
        {scopedAgents.map((agent) => {
          const alert = agentAlert(agent)
          const status = !agent.is_live
            ? 'בקרוב'
            : agent.process_alive
              ? 'חי'
              : 'לא רץ'
          return (
            <article key={agent.id} className="agent-cube">
              <header>
                <div>
                  <h3>{agent.display_name}</h3>
                  <p>{agent.role_label}</p>
                </div>
                <span
                  className={
                    !agent.is_live ? 'pill wait' : agent.process_alive ? 'pill ok' : 'pill down'
                  }
                >
                  {status}
                </span>
              </header>
              {alert ? <p className="card-alert">{alert}</p> : null}
              <p className="agent-meta">הודעה אחרונה: {relativeHe(agent.last_telegram_at)}</p>
              <ul>
                {KINDS.map((kind) => {
                  const conn = agent.connections.find((c) => c.kind === kind)
                  return (
                    <li key={kind}>
                      <span>{connectionLabel(kind)}</span>
                      {conn ? (
                        <em className={conn.connected ? 'ok' : 'down'}>
                          {conn.connected ? 'מחובר' : 'מנותק'}
                        </em>
                      ) : (
                        <em>—</em>
                      )}
                    </li>
                  )
                })}
              </ul>
            </article>
          )
        })}
      </section>
    </div>
  )
}
