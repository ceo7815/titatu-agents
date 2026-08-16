-- Titatu Agents ops dashboard (read-only for authenticated users).
-- No quote content, no customer PII.

create table public.agents (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  display_name text not null,
  role_label text not null default '',
  is_live boolean not null default false,
  created_at timestamptz not null default now()
);

create table public.agent_connections (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references public.agents (id) on delete cascade,
  kind text not null check (kind in ('telegram', 'wordpress', 'openai')),
  label text not null,
  connected boolean not null default false,
  unique (agent_id, kind)
);

create index agent_connections_agent_id_idx on public.agent_connections (agent_id);

create table public.agent_heartbeats (
  agent_id uuid primary key references public.agents (id) on delete cascade,
  process_alive boolean not null default false,
  last_heartbeat_at timestamptz,
  last_telegram_at timestamptz,
  updated_at timestamptz not null default now()
);

create table public.usage_events (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references public.agents (id) on delete cascade,
  provider text not null default 'openai',
  model text not null,
  prompt_tokens integer not null default 0,
  completion_tokens integer not null default 0,
  cost_usd numeric(12, 6) not null,
  created_at timestamptz not null default now()
);

create index usage_events_agent_created_idx
  on public.usage_events (agent_id, created_at desc);

create index usage_events_created_idx
  on public.usage_events (created_at desc);

create table public.activity_events (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references public.agents (id) on delete cascade,
  direction text not null check (direction in ('in', 'out')),
  created_at timestamptz not null default now()
);

create index activity_events_agent_created_idx
  on public.activity_events (agent_id, created_at desc);

create index activity_events_created_idx
  on public.activity_events (created_at desc);

alter table public.agents enable row level security;
alter table public.agent_connections enable row level security;
alter table public.agent_heartbeats enable row level security;
alter table public.usage_events enable row level security;
alter table public.activity_events enable row level security;

create policy agents_select_authenticated
  on public.agents for select to authenticated using (true);

create policy agent_connections_select_authenticated
  on public.agent_connections for select to authenticated using (true);

create policy agent_heartbeats_select_authenticated
  on public.agent_heartbeats for select to authenticated using (true);

create policy usage_events_select_authenticated
  on public.usage_events for select to authenticated using (true);

create policy activity_events_select_authenticated
  on public.activity_events for select to authenticated using (true);

revoke all on table public.agents from anon, public;
revoke all on table public.agent_connections from anon, public;
revoke all on table public.agent_heartbeats from anon, public;
revoke all on table public.usage_events from anon, public;
revoke all on table public.activity_events from anon, public;

grant select on table public.agents to authenticated;
grant select on table public.agent_connections to authenticated;
grant select on table public.agent_heartbeats to authenticated;
grant select on table public.usage_events to authenticated;
grant select on table public.activity_events to authenticated;
