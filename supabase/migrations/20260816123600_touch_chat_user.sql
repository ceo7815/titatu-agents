-- Register paired Telegram users on the chats screen without a dummy message.

create or replace function public.ops_touch_chat_user(
  p_secret text,
  p_agent_slug text,
  p_platform text default 'telegram',
  p_platform_user_id text default '',
  p_display_name text default ''
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
    null,
    ''
  )
  on conflict (agent_id, platform, platform_user_id) do update
    set display_name = case
          when excluded.display_name <> '' and excluded.display_name <> 'משתמש'
            then excluded.display_name
          else public.chat_users.display_name
        end;
end;
$$;

revoke all on function public.ops_touch_chat_user(text, text, text, text, text) from public;
grant execute on function public.ops_touch_chat_user(text, text, text, text, text)
  to anon, service_role;
