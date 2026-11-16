-- One profile per Supabase auth user. Role is chosen at sign-up and never changes (backend plan §6).
-- Created by the API on first sign-in through app.create_profile, not by a trigger on auth.users.

create table profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  role        text not null check (role in ('landlord', 'tenant')),
  name        text not null check (length(name) between 1 and 200),
  phone       text check (phone ~ '^\+91[6-9][0-9]{9}$'),  -- private: never returned by any endpoint
  city        text references cities (slug),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Idempotent. Errors: Z1001 role_conflict, 22023 invalid role, 42501 not authenticated.
create or replace function app.create_profile(p_role text, p_name text) returns profiles
  language plpgsql security definer set search_path = public, pg_temp
as $$
declare
  v_uid uuid := app.current_user_id();
  v_row profiles;
begin
  if v_uid is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  if p_role not in ('landlord', 'tenant') then
    raise exception 'invalid role' using errcode = '22023';
  end if;

  select * into v_row from profiles where id = v_uid;
  if found then
    if v_row.role <> p_role then
      raise exception 'role_conflict' using errcode = 'Z1001';
    end if;
    return v_row;
  end if;

  insert into profiles (id, role, name) values (v_uid, p_role, btrim(p_name)) returning * into v_row;
  return v_row;
end
$$;
revoke all on function app.create_profile(text, text) from public;
grant execute on function app.create_profile(text, text) to rentfit_api;
