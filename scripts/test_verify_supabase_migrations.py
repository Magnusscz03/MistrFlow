import tempfile
import unittest
from pathlib import Path

from verify_supabase_migrations import check_sql, verify


GOOD = """
CREATE TABLE public.jobs (id uuid primary key);
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.jobs FROM anon;
GRANT SELECT, INSERT, UPDATE ON public.jobs TO authenticated;
CREATE POLICY jobs_read ON public.jobs FOR SELECT TO authenticated
  USING ((select auth.uid()) = user_id);
CREATE POLICY jobs_write ON public.jobs FOR UPDATE TO authenticated
  USING ((select auth.uid()) = user_id)
  WITH CHECK ((select auth.uid()) = user_id);
"""


class MigrationSafetyTests(unittest.TestCase):
    def failures(self, sql: str) -> list[str]:
        return check_sql(Path("migrations/test.sql"), sql)

    def test_safe_migration_passes(self):
        self.assertEqual(self.failures(GOOD), [])

    def test_public_table_requires_rls(self):
        failures = self.failures(GOOD.replace(
            "ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;", ""
        ))
        self.assertTrue(any("without ENABLE ROW LEVEL SECURITY" in item for item in failures))

    def test_each_data_api_role_needs_explicit_decision(self):
        failures = self.failures(GOOD.replace("REVOKE ALL ON public.jobs FROM anon;", ""))
        self.assertTrue(any("no explicit GRANT or REVOKE for anon" in item for item in failures))

    def test_deprecated_auth_role_is_rejected(self):
        self.assertTrue(any("auth.role() is deprecated" in item for item in self.failures(
            GOOD + "CREATE POLICY bad ON public.jobs USING (auth.role() = 'authenticated');"
        )))

    def test_user_metadata_authorization_is_rejected(self):
        self.assertTrue(any("user_metadata" in item for item in self.failures(
            GOOD + "CREATE POLICY bad ON public.jobs USING (auth.jwt()->'user_metadata' is not null);"
        )))

    def test_update_policy_requires_with_check(self):
        sql = GOOD.replace(
            "WITH CHECK ((select auth.uid()) = user_id);",
            ";",
        )
        self.assertTrue(any("UPDATE policy is missing WITH CHECK" in item for item in self.failures(sql)))

    def test_public_security_definer_is_rejected(self):
        sql = GOOD + """
        CREATE FUNCTION public.is_owner() RETURNS boolean
        LANGUAGE sql SECURITY DEFINER AS $$ SELECT true $$;
        """
        self.assertTrue(any("SECURITY DEFINER" in item for item in self.failures(sql)))

    def test_repository_runner_reads_all_sql_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "migrations").mkdir()
            (root / "migrations" / "001.sql").write_text(GOOD, encoding="utf-8")
            checked, failures = verify(root)
        self.assertEqual(checked, 1)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
