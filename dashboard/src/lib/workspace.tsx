import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { loadAgents } from './data'
import type { Agent } from './types'

export const ALL_AGENTS = 'all'

type WorkspaceValue = {
  agents: Agent[]
  selectedId: string
  setSelectedId: (id: string) => void
  scopedAgents: Agent[]
  loading: boolean
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedId, setSelectedId] = useState(ALL_AGENTS)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAgents()
      .then(setAgents)
      .finally(() => setLoading(false))
  }, [])

  const scopedAgents = useMemo(() => {
    if (selectedId === ALL_AGENTS) return agents
    return agents.filter((agent) => agent.id === selectedId)
  }, [agents, selectedId])

  const value = useMemo(
    () => ({ agents, selectedId, setSelectedId, scopedAgents, loading }),
    [agents, selectedId, scopedAgents, loading],
  )

  return (
    <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
  )
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext)
  if (!value) throw new Error('WorkspaceProvider missing')
  return value
}
