begin;

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
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table slider_items
add column if not exists updated_at timestamptz not null default now();

create or replace function armodel_site_content_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists site_settings_set_updated_at on site_settings;
create trigger site_settings_set_updated_at
before update on site_settings
for each row execute function armodel_site_content_set_updated_at();

drop trigger if exists slider_items_set_updated_at on slider_items;
create trigger slider_items_set_updated_at
before update on slider_items
for each row execute function armodel_site_content_set_updated_at();

create index if not exists slider_items_active_sort_idx
on slider_items (sort_order, created_at)
where active = true;

insert into site_settings (key, value)
values
  ('landing_cover', 'pic/og-cover.jpg'),
  ('landing_headline', 'ภูพาน AR สกลนคร'),
  ('landing_subheadline', 'เรียนรู้ศูนย์ศึกษาการพัฒนาภูพานผ่านโมเดล 3D และ AR'),
  ('landing_description', 'เว็บไซต์รวบรวมวัตถุ ผลิตภัณฑ์ องค์ความรู้ และของดีสกลนครจากศูนย์ศึกษาการพัฒนาภูพานอันเนื่องมาจากพระราชดำริ บ้านนานกเค้า ตำบลห้วยยาง อำเภอเมือง จังหวัดสกลนคร ในรูปแบบโมเดลสามมิติและเทคโนโลยี AR'),
  ('landing_cta_text', 'เข้าสู่เว็บไซต์'),
  ('landing_cta_url', '/home'),
  ('site_logo', ''),
  ('site_name', 'PhuPhan-AR | ภูพาน AR สกลนคร'),
  ('favicon', 'favicon.ico'),
  ('meta_description', 'สำรวจศูนย์ศึกษาการพัฒนาภูพานอันเนื่องมาจากพระราชดำริ จังหวัดสกลนคร ผ่านโมเดล 3D และ AR รวมวัตถุ ผลิตภัณฑ์ ภูมิปัญญา และของดีสกลนครในรูปแบบดิจิทัล')
on conflict (key) do nothing;

alter table site_settings enable row level security;
alter table slider_items enable row level security;

commit;
