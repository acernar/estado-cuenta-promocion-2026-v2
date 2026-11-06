create extension if not exists pgcrypto;

create type public.user_role as enum ('admin');
create type public.concept_category as enum ('ahorro', 'actividad', 'compromiso', 'reembolso');
create type public.movement_type as enum ('ingreso', 'aplicacion', 'reembolso');
create type public.movement_status as enum ('activo', 'anulado');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null,
  role public.user_role not null default 'admin',
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.students (
  id uuid primary key default gen_random_uuid(),
  access_code text not null unique,
  full_name text not null,
  classroom text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.concepts (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  category public.concept_category not null,
  target_amount numeric(12,2) not null default 0 check (target_amount >= 0),
  description text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (name, category)
);

create table public.movements (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students(id),
  concept_id uuid not null references public.concepts(id),
  movement_type public.movement_type not null,
  amount numeric(12,2) not null check (amount > 0),
  movement_date date not null default current_date,
  note text,
  status public.movement_status not null default 'activo',
  void_reason text,
  voided_at timestamptz,
  voided_by uuid references auth.users(id),
  created_by uuid not null default auth.uid() references auth.users(id),
  created_at timestamptz not null default now()
);

create index movements_student_idx on public.movements(student_id);
create index movements_concept_idx on public.movements(concept_id);
create index movements_date_idx on public.movements(movement_date desc);

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'admin' and active
  );
$$;

create or replace view public.movement_detail
with (security_invoker = true) as
select m.id, m.student_id, s.full_name as student, s.access_code,
       c.name as concept, c.category, m.movement_type, m.amount,
       m.movement_date, m.note, m.status, m.void_reason, m.created_at,
       coalesce(p.full_name, 'Administrador') as registered_by
from public.movements m
join public.students s on s.id = m.student_id
join public.concepts c on c.id = m.concept_id
left join public.profiles p on p.id = m.created_by;

create or replace function public.get_student_statement(p_access_code text)
returns jsonb language plpgsql security definer set search_path = public
as $$
declare
  v_student public.students;
  v_income numeric := 0;
  v_applied numeric := 0;
  v_refunds numeric := 0;
begin
  select * into v_student from public.students
  where access_code = trim(p_access_code) and active limit 1;
  if not found then return null; end if;

  select
    coalesce(sum(amount) filter (where movement_type = 'ingreso'), 0),
    coalesce(sum(amount) filter (where movement_type = 'aplicacion'), 0),
    coalesce(sum(amount) filter (where movement_type = 'reembolso'), 0)
  into v_income, v_applied, v_refunds
  from public.movements where student_id = v_student.id and status = 'activo';

  return jsonb_build_object(
    'student', jsonb_build_object('full_name', v_student.full_name, 'classroom', v_student.classroom),
    'summary', jsonb_build_object(
      'total_income', v_income, 'total_applied', v_applied,
      'total_refunds', v_refunds, 'available_funds', v_income - v_applied - v_refunds
    ),
    'commitments', coalesce((
      select jsonb_agg(x order by x.name) from (
        select c.name, c.target_amount,
               coalesce(sum(m.amount) filter (where m.status = 'activo' and m.movement_type = 'aplicacion'), 0) as paid_amount,
               greatest(c.target_amount - coalesce(sum(m.amount) filter (where m.status = 'activo' and m.movement_type = 'aplicacion'), 0), 0) as pending_amount
        from public.concepts c
        left join public.movements m on m.concept_id = c.id and m.student_id = v_student.id
        where c.category = 'compromiso' and c.active
        group by c.id, c.name, c.target_amount
      ) x
    ), '[]'::jsonb),
    'movements', coalesce((
      select jsonb_agg(jsonb_build_object(
        'Fecha', m.movement_date, 'Concepto', c.name,
        'Tipo', m.movement_type, 'Monto', m.amount, 'Observación', m.note
      ) order by m.movement_date desc, m.created_at desc)
      from public.movements m join public.concepts c on c.id = m.concept_id
      where m.student_id = v_student.id and m.status = 'activo'
    ), '[]'::jsonb)
  );
end;
$$;

create or replace function public.void_movement(p_movement_id uuid, p_reason text)
returns void language plpgsql security definer set search_path = public
as $$
begin
  if not public.is_admin() then raise exception 'Acceso denegado'; end if;
  if nullif(trim(p_reason), '') is null then raise exception 'Debe indicar un motivo'; end if;
  update public.movements set status = 'anulado', void_reason = trim(p_reason),
    voided_at = now(), voided_by = auth.uid()
  where id = p_movement_id and status = 'activo';
  if not found then raise exception 'Movimiento no encontrado o ya anulado'; end if;
end;
$$;

alter table public.profiles enable row level security;
alter table public.students enable row level security;
alter table public.concepts enable row level security;
alter table public.movements enable row level security;

create policy profiles_admin_read on public.profiles for select using (public.is_admin());
create policy students_admin_all on public.students for all using (public.is_admin()) with check (public.is_admin());
create policy concepts_admin_all on public.concepts for all using (public.is_admin()) with check (public.is_admin());
create policy movements_admin_read on public.movements for select using (public.is_admin());
create policy movements_admin_insert on public.movements for insert with check (public.is_admin() and created_by = auth.uid());

grant execute on function public.get_student_statement(text) to anon, authenticated;
grant execute on function public.void_movement(uuid, text) to authenticated;

