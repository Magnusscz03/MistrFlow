-- Read-only Supabase security audit for MistrFlow.
-- Expected result: zero rows. This script never changes data or schema.

with findings as (
  select
    'rls_disabled'::text as finding_type,
    format('%I.%I', n.nspname, c.relname) as object_name,
    'base table in exposed public schema has RLS disabled'::text as detail
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind in ('r', 'p')
    and not c.relrowsecurity

  union all

  select
    'policy_uses_user_metadata',
    format('%I.%I / %s', schemaname, tablename, policyname),
    'policy references user-editable metadata'
  from pg_policies
  where schemaname = 'public'
    and (coalesce(qual, '') || ' ' || coalesce(with_check, ''))
      ~* '(raw_)?user_meta_data|user_metadata'

  union all

  select
    'security_definer_executable_by_api_role',
    format('%I.%I(%s)', n.nspname, p.proname,
           pg_get_function_identity_arguments(p.oid)),
    'SECURITY DEFINER function can be executed by anon or authenticated'
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.prosecdef
    and (has_function_privilege('anon', p.oid, 'EXECUTE')
      or has_function_privilege('authenticated', p.oid, 'EXECUTE'))

  union all

  select
    'api_view_without_security_invoker',
    format('%I.%I', n.nspname, c.relname),
    'view is readable by an API role without security_invoker=true'
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind = 'v'
    and not coalesce(c.reloptions, array[]::text[])
      @> array['security_invoker=true']
    and (has_table_privilege('anon', c.oid, 'SELECT')
      or has_table_privilege('authenticated', c.oid, 'SELECT'))
)
select finding_type, object_name, detail
from findings
order by finding_type, object_name;
