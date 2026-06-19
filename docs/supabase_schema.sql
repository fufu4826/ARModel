create table if not exists site_settings (
  id bigint generated always as identity primary key,
  key text unique not null,
  value text,
  updated_at timestamptz not null default now()
);

create table if not exists slider_items (
  id text primary key,
  title text not null,
  description text,
  image_url text,
  button_text text,
  button_url text,
  sort_order integer not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists site_settings_set_updated_at on site_settings;
create trigger site_settings_set_updated_at
before update on site_settings
for each row execute function set_updated_at();
