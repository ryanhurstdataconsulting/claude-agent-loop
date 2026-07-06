import json, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import distill_transcripts as dt

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class TestExtraction(unittest.TestCase):
    def test_extracts_user_and_assistant_text_only(self):
        lines = (FIXTURES / "proj-a" / "session1.jsonl").read_text().splitlines()
        texts = [t for line in lines for t in dt.extract_texts(json.loads(line))]
        joined = "\n".join(texts)
        self.assertIn("please pull the cohort", joined)
        self.assertIn("Here is the plan", joined)
        self.assertNotIn("TOOL_RESULT_NOISE", joined)   # tool_result skipped
        self.assertNotIn("echo tool_use", joined)       # tool_use skipped
        self.assertNotIn("summary line", joined)        # non-user/assistant skipped

    def test_strips_system_reminders(self):
        rec = {"type": "user", "message": {"content":
              "hi <system-reminder>injected protocol</system-reminder> there"}}
        self.assertEqual(dt.extract_texts(rec), ["hi  there"])


class TestRedaction(unittest.TestCase):
    CASES = [
        ("jwt", "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.c2lnbmF0dXJl end",
         "eyJhbGciOiJIUzI1NiJ9", "[REDACTED-JWT]"),
        ("bearer", "Authorization: Bearer abc123.def-456xyz", "abc123.def-456xyz",
         "[REDACTED-TOKEN]"),
        ("password", "password=hunter2 ok", "hunter2", "[REDACTED-SECRET]"),
        ("api_key", "API_KEY: sk-lots-of-entropy-here", "sk-lots-of-entropy-here",
         "[REDACTED-SECRET]"),
        ("db_uri", "postgres://user:pw@host:5432/db", "user:pw@host", "[REDACTED-DB-URI]"),
        ("pem", "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAAfakekey\n-----END OPENSSH PRIVATE KEY-----",
         "AAAAfakekey", "[REDACTED-PEM]"),
        ("email", "contact coach@example.co.za today", "coach@example.co.za",
         "[REDACTED-EMAIL]"),
        ("phone", "call +1 (510) 555-0123 now", "555-0123", "[REDACTED-PHONE]"),
        ("phone_dashed", "call 555-123-4567 now", "555-123-4567", "[REDACTED-PHONE]"),
        ("phone_parens", "call (555) 123-4567 now", "123-4567", "[REDACTED-PHONE]"),
    ]

    def test_redaction_branches(self):
        for label, dirty, secret, marker in self.CASES:
            with self.subTest(label=label):
                clean, counts = dt.redact(dirty)
                self.assertIn(marker, clean)
                self.assertNotIn(secret, clean)
                self.assertGreaterEqual(sum(counts.values()), 1)

    def test_row_counts_survive_phone_heuristic(self):
        clean, _ = dt.redact("the cohort has 12785 athletes and 5173 in dev, ref 5551234567")
        self.assertIn("12785", clean)
        self.assertIn("5173", clean)
        self.assertIn("5551234567", clean)  # bare digit runs may be IDs — left intact


class TestRouting(unittest.TestCase):
    def test_one_output_file_per_project(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td)
            stats = dt.distill(FIXTURES, out)
            self.assertTrue((out / "proj-a.md").exists())
            self.assertTrue((out / "proj-b.md").exists())
            self.assertEqual(stats["proj-a"]["sessions"], 1)
            self.assertGreaterEqual(stats["proj-a"]["redactions"], 1)

    def test_prefix_filter(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td)
            stats = dt.distill(FIXTURES, out, prefix="proj-a")
            self.assertIn("proj-a", stats)
            self.assertNotIn("proj-b", stats)

    def test_output_contains_no_jwt_shapes(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td)
            dt.distill(FIXTURES, out)
            for f in out.glob("*.md"):
                self.assertNotRegex(f.read_text(), r"eyJ[A-Za-z0-9_-]{10,}\.")


if __name__ == "__main__":
    unittest.main()
