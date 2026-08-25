from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "db/schema.sql").read_text(encoding="utf-8").lower()
POLICY = (ROOT / "db/policy.sql").read_text(encoding="utf-8").lower()
PACKAGE = (ROOT / "web/package.json").read_text(encoding="utf-8").lower()


class PolicyTests(unittest.TestCase):
    def test_read_only(self) -> None:
        self.assertIn("enable row level security", SCHEMA)
        self.assertIn("revoke all", POLICY)
        self.assertIn("grant select", POLICY)
        self.assertNotIn("grant insert", POLICY)
        self.assertNotIn("grant update", POLICY)
        self.assertNotIn("grant delete", POLICY)

    def test_safe_search(self) -> None:
        self.assertIn("security invoker", SCHEMA)
        self.assertIn("websearch_to_tsquery", SCHEMA)
        self.assertIn("search_corpus", SCHEMA)
        self.assertIn("greatest(coalesce(page_size", SCHEMA)
        self.assertNotIn("execute format", SCHEMA)

    def test_public_scope(self) -> None:
        self.assertNotIn("service_role", POLICY)
        self.assertNotIn("storage", SCHEMA)
        self.assertNotIn("pdf", SCHEMA)

    def test_no_workspace(self) -> None:
        self.assertNotIn("workspace", SCHEMA)
        self.assertNotIn("create table public.users", SCHEMA)
        self.assertNotIn("@supabase/auth", PACKAGE)

    def test_query_bounds(self) -> None:
        self.assertIn("statement_timeout = '3s'", SCHEMA)
        self.assertIn("left(trim(search_query), 256)", SCHEMA)
        self.assertIn("10000", SCHEMA)


if __name__ == "__main__":
    unittest.main()
