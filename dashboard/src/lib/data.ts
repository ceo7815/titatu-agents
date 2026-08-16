import { supabase } from './supabase'
import {
  monthJerusalem,
  todayJerusalem,
  toJerusalemDay,
  toJerusalemMonth,
} from './format'
import type {
  ActivityEvent,
  Agent,
  AgentConnection,
  ChatMessage,
  ChatUser,
  ConnectionKind,
  DailyCost,
  MonthlyCost,
  UsageEvent,
} from './types'

type AgentRow = {
  id: string
  slug: string
  display_name: string
  role_label: string
  is_live: boolean
  agent_connections: AgentConnection[] | null
  agent_heartbeats:
    | {
        process_alive: boolean
        last_heartbeat_at: string | null
        last_telegram_at: string | null
      }
    | {
        process_alive: boolean
        last_heartbeat_at: string | null
        last_telegram_at: string | null
      }[]
    | null
}

function asHeartbeat(value: AgentRow['agent_heartbeats']) {
  if (!value) return null
  return Array.isArray(value) ? value[0] ?? null : value
}

export async function loadAgents(): Promise<Agent[]> {
  const { data, error } = await supabase
    .from('agents')
    .select(
      'id, slug, display_name, role_label, is_live, agent_connections(kind, label, connected), agent_heartbeats(process_alive, last_heartbeat_at, last_telegram_at)',
    )
    .order('created_at', { ascending: true })

  if (error) throw error

  return ((data ?? []) as AgentRow[]).map((row) => {
    const hb = asHeartbeat(row.agent_heartbeats)
    return {
      id: row.id,
      slug: row.slug,
      display_name: row.display_name,
      role_label: row.role_label,
      is_live: row.is_live,
      process_alive: hb?.process_alive ?? false,
      last_heartbeat_at: hb?.last_heartbeat_at ?? null,
      last_telegram_at: hb?.last_telegram_at ?? null,
      connections: (row.agent_connections ?? []) as AgentConnection[],
    }
  })
}

/** Official OpenAI gpt-4.1-mini standard prices, USD per 1M tokens. */
export const GPT41_MINI = {
  inputPerMillion: 0.4,
  cachedPerMillion: 0.1,
  outputPerMillion: 1.6,
}

export function costFromTokens(
  promptTokens: number,
  completionTokens: number,
  cacheReadTokens = 0,
): number {
  const cached = Math.max(cacheReadTokens, 0)
  const input = Math.max(promptTokens - cached, 0)
  return (
    (input * GPT41_MINI.inputPerMillion +
      cached * GPT41_MINI.cachedPerMillion +
      Math.max(completionTokens, 0) * GPT41_MINI.outputPerMillion) /
    1_000_000
  )
}

export async function loadUsage90d(): Promise<UsageEvent[]> {
  const since = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString()
  const { data, error } = await supabase
    .from('usage_events')
    .select(
      'id, agent_id, provider, model, prompt_tokens, completion_tokens, cache_read_tokens, cost_usd, created_at',
    )
    .gte('created_at', since)
    .order('created_at', { ascending: true })

  if (error) throw error
  return (data ?? []).map((row) => {
    const prompt_tokens = Number(row.prompt_tokens ?? 0)
    const completion_tokens = Number(row.completion_tokens ?? 0)
    const cache_read_tokens = Number(row.cache_read_tokens ?? 0)
    return {
      id: String(row.id),
      agent_id: String(row.agent_id),
      provider: String(row.provider ?? 'openai'),
      model: String(row.model ?? 'gpt-4.1-mini'),
      prompt_tokens,
      completion_tokens,
      cache_read_tokens,
      created_at: String(row.created_at),
      cost_usd: costFromTokens(prompt_tokens, completion_tokens, cache_read_tokens),
    }
  })
}

export async function loadActivity(): Promise<ActivityEvent[]> {
  const { data, error } = await supabase
    .from('activity_events')
    .select('id, agent_id, direction, created_at, agents(display_name)')
    .order('created_at', { ascending: false })
    .limit(150)

  if (error) throw error

  return ((data ?? []) as Array<{
    id: string
    agent_id: string
    direction: 'in' | 'out'
    created_at: string
    agents: { display_name: string } | { display_name: string }[] | null
  }>).map((row) => {
    const agent = Array.isArray(row.agents) ? row.agents[0] : row.agents
    return {
      id: row.id,
      agent_id: row.agent_id,
      direction: row.direction,
      created_at: row.created_at,
      agent_name: agent?.display_name ?? 'סוכן',
    }
  })
}

export async function loadChatUsers(): Promise<ChatUser[]> {
  const { data, error } = await supabase
    .from('chat_users')
    .select('id, agent_id, platform, platform_user_id, display_name, last_message_at, last_preview')
    .order('last_message_at', { ascending: false })

  if (error) throw error
  return (data ?? []) as ChatUser[]
}

export async function loadChatMessages(chatUserId: string): Promise<ChatMessage[]> {
  const { data, error } = await supabase
    .from('chat_messages')
    .select('id, agent_id, chat_user_id, direction, body, created_at')
    .eq('chat_user_id', chatUserId)
    .order('created_at', { ascending: true })
    .limit(500)

  if (error) throw error
  return (data ?? []) as ChatMessage[]
}

export function agentAlert(agent: Agent): string | null {
  if (!agent.is_live) return null
  if (!agent.process_alive) return `${agent.display_name} לא רץ כרגע`
  const openai = agent.connections.find((c) => c.kind === 'openai')
  const telegram = agent.connections.find((c) => c.kind === 'telegram')
  if (telegram && !telegram.connected) return `טלגרם של ${agent.display_name} מנותק`
  if (openai && !openai.connected) return `OpenAI של ${agent.display_name} מנותק`
  return null
}

export function connectionLabel(kind: ConnectionKind): string {
  if (kind === 'telegram') return 'טלגרם'
  if (kind === 'wordpress') return 'וורדפרס'
  return 'OpenAI'
}

export function rollupDaily(events: UsageEvent[]): DailyCost[] {
  const map = new Map<string, DailyCost>()
  for (const event of events) {
    const day = toJerusalemDay(event.created_at)
    const current = map.get(day) ?? {
      day,
      cost_usd: 0,
      calls: 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      cache_read_tokens: 0,
    }
    current.cost_usd += event.cost_usd
    current.calls += 1
    current.prompt_tokens += event.prompt_tokens
    current.completion_tokens += event.completion_tokens
    current.cache_read_tokens += event.cache_read_tokens
    map.set(day, current)
  }
  return [...map.values()].sort((a, b) => a.day.localeCompare(b.day))
}

export function rollupMonthly(events: UsageEvent[]): MonthlyCost[] {
  const map = new Map<string, MonthlyCost>()
  for (const event of events) {
    const month = toJerusalemMonth(event.created_at)
    const current = map.get(month) ?? {
      month,
      cost_usd: 0,
      calls: 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      cache_read_tokens: 0,
    }
    current.cost_usd += event.cost_usd
    current.calls += 1
    current.prompt_tokens += event.prompt_tokens
    current.completion_tokens += event.completion_tokens
    current.cache_read_tokens += event.cache_read_tokens
    map.set(month, current)
  }
  return [...map.values()].sort((a, b) => b.month.localeCompare(a.month))
}

export function tokenTotals(events: UsageEvent[]) {
  return events.reduce(
    (sum, event) => {
      sum.prompt += event.prompt_tokens
      sum.completion += event.completion_tokens
      sum.cached += event.cache_read_tokens
      sum.calls += 1
      sum.cost += event.cost_usd
      return sum
    },
    { prompt: 0, completion: 0, cached: 0, calls: 0, cost: 0 },
  )
}

export function sumToday(events: UsageEvent[], agentId?: string): number {
  const today = todayJerusalem()
  return events
    .filter((e) => (!agentId || e.agent_id === agentId) && toJerusalemDay(e.created_at) === today)
    .reduce((sum, e) => sum + e.cost_usd, 0)
}

export function sumMonth(events: UsageEvent[], agentId?: string): number {
  const month = monthJerusalem()
  return events
    .filter((e) => (!agentId || e.agent_id === agentId) && toJerusalemMonth(e.created_at) === month)
    .reduce((sum, e) => sum + e.cost_usd, 0)
}

export function last90Days(): string[] {
  const days: string[] = []
  const now = new Date()
  for (let i = 89; i >= 0; i -= 1) {
    const d = new Date(now.getTime() - i * 24 * 60 * 60 * 1000)
    days.push(
      new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Jerusalem',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).format(d),
    )
  }
  return days
}
