import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "deploy/source-sync/linux/source-sync-alert.sh"


@unittest.skipIf(os.name == "nt" or not shutil.which("bash"), "POSIX shell integration test")
class SourceSyncAlertBehavior(unittest.TestCase):
    def run_helper(self, mode, report):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "sources.enc.json").write_text("fixture", encoding="utf-8")
            verifier = directory / "verify.py"
            verifier.write_text("import os\nprint(os.environ['FAKE_REPORT'])\n", encoding="utf-8")
            fake = directory / "alert.py"
            fake.write_text("#!" + sys.executable + "\nimport os,sys,json\n"
                            "with open(os.environ['FAKE_ALERT_LOG'],'a',encoding='utf-8') as f:\n"
                            " f.write(json.dumps(sys.argv[1:])+'\\n')\n", encoding="utf-8")
            fake.chmod(0o755)
            logfile = directory / "calls.jsonl"
            environment = dict(os.environ)
            environment.update({
                "MAGNET_ALERT_BIN": str(fake), "MAGNET_SOURCE_PYTHON_BIN": sys.executable,
                "MAGNET_SOURCE_VERIFIER": str(verifier), "MAGNET_SOURCE_TARGET_ROOT": str(directory),
                "MAGNET_SOURCE_SYNC_ALERT_STATE": str(directory / "sync.json"),
                "MAGNET_SOURCE_EXPIRY_ALERT_STATE": str(directory / "expiry.json"),
                "MAGNET_SOURCE_EXPIRY_OBSERVATION_STATE": str(directory / "observation.json"),
                "FAKE_REPORT": report, "FAKE_ALERT_LOG": str(logfile)})
            result = subprocess.run(["bash", str(HELPER), mode], env=environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    universal_newlines=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in logfile.read_text().splitlines()]
            return [(args[0], args[args.index("--key") + 1]) for args in calls]

    def test_failed_sync_still_checks_expiry(self):
        calls = self.run_helper("failure", '{"full":{"remaining_hours":12}}')
        self.assertIn(("failure", "source-sync"), calls)
        self.assertIn(("failure", "source-expiry"), calls)

    def test_unknown_expiry_cannot_recover(self):
        calls = self.run_helper("success", '{"full":{}}')
        self.assertIn(("failure", "source-expiry-observation"), calls)
        self.assertNotIn(("success", "source-expiry"), calls)

    def test_malformed_verifier_cannot_recover(self):
        calls = self.run_helper("success", "not-json")
        self.assertIn(("failure", "source-expiry-observation"), calls)
        self.assertNotIn(("success", "source-expiry"), calls)

    def test_nonfinite_expiry_cannot_recover(self):
        for value in ("NaN", "Infinity"):
            calls = self.run_helper("success", json.dumps({"full": {"remaining_hours": value}}))
            self.assertIn(("failure", "source-expiry-observation"), calls)
            self.assertNotIn(("success", "source-expiry"), calls)

    def test_valid_safe_expiry_can_recover(self):
        calls = self.run_helper("success", '{"full":{"remaining_hours":48}}')
        self.assertIn(("success", "source-expiry-observation"), calls)
        self.assertIn(("success", "source-expiry"), calls)


if __name__ == "__main__":
    unittest.main()
