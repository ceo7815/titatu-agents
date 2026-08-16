-- Chat history per Telegram user. Dashboard remains SELECT-only.

create table if not exists public.chat_users (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references public.agents (id) on delete cascade,
  platform text not null default 'telegram',
  platform_user_id text not null,
  display_name text not null default '',
  last_message_at timestamptz,
  last_preview text not null default '',
  created_at timestamptz not null default now(),
  unique (agent_id, platform, platform_user_id)
);

create index chat_users_agent_last_idx
  on public.chat_users (agent_id, last_message_at desc);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references public.agents (id) on delete cascade,
  chat_user_id uuid not null references public.chat_users (id) on delete cascade,
  direction text not null check (direction in ('in', 'out')),
  body text not null default '',
  created_at timestamptz not null default now()
);

create index chat_messages_user_created_idx
  on public.chat_messages (chat_user_id, created_at);

alter table public.chat_users enable row level security;
alter table public.chat_messages enable row level security;

create policy chat_users_select_authenticated
  on public.chat_users for select to authenticated using (true);

create policy chat_messages_select_authenticated
  on public.chat_messages for select to authenticated using (true);

revoke all on table public.chat_users from anon, public;
revoke all on table public.chat_messages from anon, public;
grant select on table public.chat_users to authenticated;
grant select on table public.chat_messages to authenticated;

create or replace function public.ops_log_chat(
  p_secret text,
  p_agent_slug text,
  p_direction text,
  p_platform text default 'telegram',
  p_platform_user_id text default '',
  p_display_name text default '',
  p_body text default ''
) returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  aid uuid;
  uid uuid;
  preview text;
  body text;
begin
  perform public.ops_assert_secret(p_secret);
  if p_direction not in ('in', 'out') then
    raise exception 'bad direction';
  end if;
  aid := public.ops_agent_id(p_agent_slug);
  if aid is null then
    raise exception 'unknown agent';
  end if;

  body := left(coalesce(p_body, ''), 8000);
  preview := left(regexp_replace(body, E'[\\n\\r]+', ' ', 'g'), 140);

  insert into public.activity_events (agent_id, direction) values (aid, p_direction);
  insert into public.agent_heartbeats (
    agent_id, process_alive, last_heartbeat_at, last_telegram_at, updated_at
  ) values (aid, true, now(), now(), now())
  on conflict (agent_id) do update
    set process_alive = true,
        last_heartbeat_at = excluded.last_heartbeat_at,
        last_telegram_at = excluded.last_telegram_at,
        updated_at = excluded.updated_at;

  if coalesce(nullif(p_platform_user_id, ''), '') is null then
    return;
  end if;

  insert into public.chat_users (
    agent_id, platform, platform_user_id, display_name, last_message_at, last_preview
  ) values (
    aid,
    coalesce(nullif(p_platform, ''), 'telegram'),
    p_platform_user_id,
    coalesce(nullif(p_display_name, ''), 'משתמש'),
    now(),
    preview
  )
  on conflict (agent_id, platform, platform_user_id) do update
    set display_name = case
          when excluded.display_name <> '' and excluded.display_name <> 'משתמש'
            then excluded.display_name
          else public.chat_users.display_name
        end,
        last_message_at = excluded.last_message_at,
        last_preview = excluded.last_preview
    returning id into uid;

  if uid is null then
    select id into uid
    from public.chat_users
    where agent_id = aid
      and platform = coalesce(nullif(p_platform, ''), 'telegram')
      and platform_user_id = p_platform_user_id;
  end if;

  insert into public.chat_messages (agent_id, chat_user_id, direction, body)
  values (aid, uid, p_direction, body);
end;
$$;

revoke all on function public.ops_log_chat(text, text, text, text, text, text, text) from public;
grant execute on function public.ops_log_chat(text, text, text, text, text, text, text)
  to anon, service_role;
