export type ConnectionKind = 'telegram' | 'wordpress' | 'openai'

export type AgentConnection = {
  kind: ConnectionKind
  label: string
  connected: boolean
}

export type Agent = {
  id: string
  slug: string
  display_name: string
  role_label: string
  is_live: boolean
  process_alive: boolean
  last_heartbeat_at: string | null
  last_telegram_at: string | null
  connections: AgentConnection[]
}

export type UsageEvent = {
  id: string
  agent_id: string
  provider: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  cache_read_tokens: number
  cost_usd: number
  created_at: string
}

export type ActivityEvent = {
  id: string
  agent_id: string
  direction: 'in' | 'out'
  created_at: string
  agent_name: string
}

export type ChatUser = {
  id: string
  agent_id: string
  platform: string
  platform_user_id: string
  display_name: string
  last_message_at: string | null
  last_preview: string
}

export type ChatMessage = {
  id: string
  agent_id: string
  chat_user_id: string
  direction: 'in' | 'out'
  body: string
  created_at: string
}

export type DailyCost = {
  day: string
  cost_usd: number
  calls: number
  prompt_tokens: number
  completion_tokens: number
  cache_read_tokens: number
}

export type MonthlyCost = {
  month: string
  cost_usd: number
  calls: number
  prompt_tokens: number
  completion_tokens: number
  cache_read_tokens: number
}
