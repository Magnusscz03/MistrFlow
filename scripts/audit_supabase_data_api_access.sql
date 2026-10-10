-- Read-only check for the public Data API contract used by MistrFlow.
-- Expected result: zero rows. This query does not change grants or policies.
-- It checks effective privileges, including the column-level grant used by
-- plan_catalog, so it remains valid when automatic API exposure is disabled.

with expected_column_access(role_name, table_name, column_name, privilege_name) as (
  values
    ('anon', 'plan_catalog', 'code', 'SELECT'),
    ('anon', 'plan_catalog', 'name', 'SELECT'),
    ('anon', 'plan_catalog', 'description', 'SELECT'),
    ('anon', 'plan_catalog', 'monthly_cents', 'SELECT'),
    ('anon', 'plan_catalog', 'annual_cents', 'SELECT'),
    ('anon', 'plan_catalog', 'currency', 'SELECT'),
    ('anon', 'plan_catalog', 'is_public', 'SELECT'),
    ('anon', 'plan_catalog', 'is_recommended', 'SELECT'),
    ('anon', 'plan_catalog', 'active', 'SELECT'),
    ('anon', 'plan_catalog', 'sort_order', 'SELECT')
),
expected_table_access(role_name, table_name, privilege_name, should_have) as (
  values
    ('anon', 'mobile_releases', 'SELECT', true),
    ('anon', 'customers', 'SELECT', false),
    ('anon', 'sales_inquiries', 'SELECT', false),
    ('authenticated', 'customers', 'SELECT', true),
    ('authenticated', 'appointments', 'SELECT', true),
    ('authenticated', 'invoices', 'SELECT', true),
    ('authenticated', 'attachments', 'SELECT', true)
),
column_gaps as (
  select
    'missing_expected_column_privilege'::text as finding,
    role_name,
    table_name,
    column_name,
    privilege_name,
    'required by the public pricing request'::text as detail
  from expected_column_access
  where not has_column_privilege(
    role_name,
    format('public.%I', table_name),
    column_name,
    privilege_name
  )
),
table_mismatches as (
  select
    case when should_have
      then 'missing_expected_table_privilege'
      else 'unexpected_sensitive_table_privilege'
    end::text as finding,
    role_name,
    table_name,
    null::text as column_name,
    privilege_name,
    case when should_have
      then 'required by an application read path'
      else 'anonymous access must remain denied'
    end::text as detail
  from expected_table_access
  where has_table_privilege(
    role_name,
    format('public.%I', table_name),
    privilege_name
  ) <> should_have
)
select * from column_gaps
union all
select * from table_mismatches
order by finding, role_name, table_name, column_name;
