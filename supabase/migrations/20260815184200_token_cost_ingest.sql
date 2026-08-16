-- Token-accurate usage ingest for the live agent (secret checked in RPC).
-- Dashboard stays SELECT-only.

alter table public.usage_events
  add column if not exists cache_read_tokens integer not null default 0;

alter table public.usage_events
  alter column cost_usd type numeric(14, 8);

create table if not exists public.ops_ingest_config (
  id integer primary key default 1 check (id = 1),
  secret text not null
);

alter table public.ops_ingest_config enable row level security;

revoke all on table public.ops_ingest_config from anon, authenticated, public;

create or replace function public.ops_agent_id(p_slug text)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select id from public.agents where slug = p_slug
$$;

create or replace function public.ops_assert_secret(p_secret text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_secret is null or p_secret = '' then
    raise exception 'denied';
  end if;
  if not exists (
    select 1 from public.ops_ingest_config c
    where c.id = 1 and c.secret = p_secret
  ) then
    raise exception 'denied';
  end if;
end;
$$;

create or replace function public.ops_log_usage(
  p_secret text,
  p_agent_slug text,
  p_provider text default 'openai',
  p_model text default 'gpt-4.1-mini',
  p_prompt_tokens integer default 0,
  p_completion_tokens integer default 0,
  p_cache_read_tokens integer default 0,
  p_cost_usd numeric default 0
) returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  aid uuid;
begin
  perform public.ops_assert_secret(p_secret);
  aid := public.ops_agent_id(p_agent_slug);
  if aid is null then
    raise exception 'unknown agent';
  end if;
  insert into public.usage_events (
    agent_id, provider, model, prompt_tokens, completion_tokens, cache_read_tokens, cost_usd
  ) values (
    aid,
    coalesce(nullif(p_provider, ''), 'openai'),
    coalesce(nullif(p_model, ''), 'gpt-4.1-mini'),
    greatest(coalesce(p_prompt_tokens, 0), 0),
    greatest(coalesce(p_completion_tokens, 0), 0),
    greatest(coalesce(p_cache_read_tokens, 0), 0),
    coalesce(p_cost_usd, 0)
  );
  insert into public.agent_heartbeats (agent_id, process_alive, last_heartbeat_at, updated_at)
  values (aid, true, now(), now())
  on conflict (agent_id) do update
    set process_alive = true,
        last_heartbeat_at = excluded.last_heartbeat_at,
        updated_at = excluded.updated_at;
end;
$$;

create or replace function public.ops_log_activity(
  p_secret text,
  p_agent_slug text,
  p_direction text
) returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  aid uuid;
begin
  perform public.ops_assert_secret(p_secret);
  if p_direction not in ('in', 'out') then
    raise exception 'bad direction';
  end if;
  aid := public.ops_agent_id(p_agent_slug);
  if aid is null then
    raise exception 'unknown agent';
  end if;
  insert into public.activity_events (agent_id, direction) values (aid, p_direction);
  insert into public.agent_heartbeats (
    agent_id, process_alive, last_heartbeat_at, last_telegram_at, updated_at
  ) values (aid, true, now(), now(), now())
  on conflict (agent_id) do update
    set process_alive = true,
        last_heartbeat_at = excluded.last_heartbeat_at,
        last_telegram_at = excluded.last_telegram_at,
        updated_at = excluded.updated_at;
end;
$$;

revoke all on function public.ops_agent_id(text) from public, anon, authenticated;
revoke all on function public.ops_assert_secret(text) from public, anon, authenticated;
revoke all on function public.ops_log_usage(text, text, text, text, integer, integer, integer, numeric) from public;
revoke all on function public.ops_log_activity(text, text, text) from public;

grant execute on function public.ops_log_usage(text, text, text, text, integer, integer, integer, numeric)
  to anon, service_role;
grant execute on function public.ops_log_activity(text, text, text)
  to anon, service_role;
