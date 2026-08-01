"""Tests for secret_pii_scrub_gate — the staged-content leak scanner.

Written TDD-first: this module imports ``secret_pii_scrub_gate`` before the
tool exists (RED = ModuleNotFoundError), then drives it GREEN. All fixtures are
synthetic — no real credential, token, or personal datum appears here.
"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import secret_pii_scrub_gate as gate

# --- Synthetic leak fixtures (one planted instance per class) ---------------
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig"
BEARER_TOKEN = "abc123def456"
PASSWORD_VALUE = "hunter2"
PEM_HEADER = "-----BEGIN OPENSSH PRIVATE KEY-----"
PG_URI = "postgres://u:p@h:5432/db"
EMAIL = "coach@example.com"
USER_PATH = "/Users/testuser/secret.txt"
# AWS's own published documentation example key — a real *shape*, not a real
# credential. It carries no `key = value` assignment, which is exactly why the
# generic SECRET pattern never sees it.
AWS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"

DIRTY = "\n".join([
    f"auth_jwt = {JWT}",
    f"Authorization: Bearer {BEARER_TOKEN}",
    f"password={PASSWORD_VALUE}",
    PEM_HEADER,
    f"DATABASE_URL={PG_URI}",
    f"contact {EMAIL} for access",
    f"key lives at {USER_PATH}",
])

# The seven class labels the gate must emit, one per DIRTY line.
EXPECTED_CLASSES = {
    "JWT", "BEARER", "SECRET", "PEM", "DB-URI", "EMAIL", "USERPATH",
}

# The raw secret values that must never appear verbatim in the tool's output.
SENSITIVE_VERBATIM = [
    JWT, BEARER_TOKEN, PASSWORD_VALUE, "u:p@h", EMAIL, "testuser",
]

CLEAN = "\n".join([
    "The cohort has 12785 athletes and 5173 in dev.",
    "Row count: 32.2 average, ref id 5551234567 in the ledger.",
    "See docs/README for the export runbook.",
])


class TestCleanInput(unittest.TestCase):
    def test_clean_text_has_no_findings(self):
        self.assertEqual(gate.scan_text(CLEAN, "clean.txt"), [])

    def test_numeric_row_counts_not_flagged(self):
        findings = gate.scan_text(CLEAN, "clean.txt")
        self.assertEqual(findings, [], f"false positive(s): {findings}")

    def test_clean_file_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "clean.txt"
            f.write_text(CLEAN)
            self.assertEqual(gate.main([str(f)]), 0)

    def test_clean_directory_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            (pathlib.Path(td) / "a.txt").write_text(CLEAN)
            (pathlib.Path(td) / "b.txt").write_text("nothing to see here\n")
            self.assertEqual(gate.main([td]), 0)


class TestDirtyInput(unittest.TestCase):
    def test_detects_all_seven_classes(self):
        findings = gate.scan_text(DIRTY, "fixture.txt")
        self.assertEqual(len(findings), 7, findings)
        self.assertEqual({f.cls for f in findings}, EXPECTED_CLASSES)

    def test_each_finding_is_file_line_formatted(self):
        for f in gate.scan_text(DIRTY, "fixture.txt"):
            rendered = gate.format_finding(f)
            self.assertRegex(rendered, r"^fixture\.txt:\d+: ")

    def test_output_never_echoes_a_secret_verbatim(self):
        rendered = "\n".join(
            gate.format_finding(f) for f in gate.scan_text(DIRTY, "fixture.txt")
        )
        for secret in SENSITIVE_VERBATIM:
            self.assertNotIn(secret, rendered,
                             f"redaction leaked {secret!r} into output")

    def test_dirty_file_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "leak.env"
            f.write_text(DIRTY)
            self.assertEqual(gate.main([str(f)]), 1)


class TestPerClass(unittest.TestCase):
    """Each class fires in isolation and only that class fires."""
    CASES = [
        ("JWT", f"tok = {JWT}"),
        ("BEARER", f"Authorization: Bearer {BEARER_TOKEN}"),
        ("SECRET", "api_key = sk-lots-of-entropy-here"),
        ("PEM", PEM_HEADER),
        ("DB-URI", PG_URI),
        ("EMAIL", f"reach {EMAIL} now"),
        ("USERPATH", USER_PATH),
        ("AWS-KEY", AWS_KEY_ID),
    ]

    def test_isolated_class_detection(self):
        for cls, line in self.CASES:
            with self.subTest(cls=cls):
                findings = gate.scan_text(line, "one.txt")
                self.assertEqual([f.cls for f in findings], [cls])


class TestAwsKeyId(unittest.TestCase):
    """A bare AWS access key ID is a leak on its own.

    It names the account and the principal, and it is the single most likely
    credential shape to be quoted verbatim into a generated security-findings
    document — the one artifact this gate exists to guard. It carries no
    ``key = value`` assignment, so the SECRET pattern never fires on it.
    """

    def test_bare_key_id_is_a_finding(self):
        findings = gate.scan_text(f"leaked {AWS_KEY_ID} in config", "f.txt")
        self.assertEqual([f.cls for f in findings], ["AWS-KEY"])

    def test_temporary_session_key_prefix_also_fires(self):
        findings = gate.scan_text("ASIAIOSFODNN7EXAMPLE", "f.txt")
        self.assertEqual([f.cls for f in findings], ["AWS-KEY"])

    def test_key_id_is_never_echoed_verbatim(self):
        rendered = "\n".join(
            gate.format_finding(f)
            for f in gate.scan_text(AWS_KEY_ID, "f.txt")
        )
        self.assertNotIn(AWS_KEY_ID, rendered)
        self.assertIn("[REDACTED-AWS-KEY]", rendered)

    def test_file_containing_a_key_id_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "SECURITY_AUDIT.md"
            f.write_text(f"# Audit\n\nHardcoded {AWS_KEY_ID} in the deploy script.\n")
            self.assertEqual(gate.main([str(f)]), 1)

    def test_similar_looking_prose_is_not_flagged(self):
        for benign in ("AKIA", "the AKIAIOSFO placeholder", "AKIAIOSFODNN7EXAMPLES1"):
            with self.subTest(benign=benign):
                self.assertEqual(gate.scan_text(benign, "f.txt"), [])


if __name__ == "__main__":
    unittest.main()
