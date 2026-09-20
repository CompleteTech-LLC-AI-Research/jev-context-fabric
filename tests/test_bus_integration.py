"""End-to-end jev-bus chain across BOTH packages, as real subprocesses.

Skipped unless jev-prune-kit is checked out nearby, so the ordinary suite stays
self-contained. Set JEV_PRUNE_KIT to point at that checkout to run it explicitly.

This is the check that matters most for the two-package contract: the unit tests verify each
side against a stub, and only this one proves that a real dedup stage and a real active-view
stage compose in one chain without destroying each other's work.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jev_context import bus  # noqa: E402
from jev_context.paging import message_key  # noqa: E402


def find_prune_kit() -> Path | None:
    explicit = os.environ.get("JEV_PRUNE_KIT")
    candidates = [Path(explicit)] if explicit else []
    candidates += [ROOT.parent / "jev-prune-kit", ROOT.parent / "jev-prune-kit" / "jev-prune-kit"]
    for candidate in candidates:
        if (candidate / "jev_prune" / "core.py").exists() and (candidate / "runner.py").exists():
            return candidate
    return None


PRUNE_KIT = find_prune_kit()


@unittest.skipIf(PRUNE_KIT is None, "jev-prune-kit checkout not found; set JEV_PRUNE_KIT to run")
class CrossPackageChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(PRUNE_KIT))
        sys.path.insert(0, str(PRUNE_KIT / "tests"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.workspace = self.work / "ws"
        self.workspace.mkdir()
        self.state = self.work / "state"
        self.state.mkdir()
        self.previous = os.environ.get("JEV_BUS_HOME")
        os.environ["JEV_BUS_HOME"] = str(self.work / "bus")
        self.addCleanup(self.restore)

        import fixtures
        from jev_prune.core import assess, snapshot
        from jev_prune.fsutil import ReceiptStore

        self.fixtures = fixtures
        self.messages = fixtures.opencode_messages()
        approved = assess(snapshot("opencode", "s1", self.messages), [], fixtures.yes)
        ReceiptStore(self.state, "p1").save("s1", approved["receipts"], None)
        self.assertGreater(len(approved["receipts"]), 0, "fixture must yield a dedup receipt")
        self.register_both()

    def restore(self):
        if self.previous is None:
            os.environ.pop("JEV_BUS_HOME", None)
        else:
            os.environ["JEV_BUS_HOME"] = self.previous

    def register_both(self):
        bus.register("jev-prune-kit", [{
            "name": "jev-prune.dedup@opencode", "priority": 100, "claims": ["tool-result:read"],
            "hosts": ["opencode"],
            "transport": {"kind": "subprocess-json", "argv": [
                sys.executable, str(PRUNE_KIT / "runner.py"), "--bus-stage",
                "--state-dir", str(self.state), "--profile", "p1", "--format", "opencode"]},
        }], {h: {"rank": bus.carrier_rank("jev-prune-kit", h)} for h in ("pi", "hermes", "opencode")})
        bus.register("jev-context-fabric", [{
            "name": "jev-context.view", "priority": 200,
            "claims": ["assistant-prose", "message-remove", "system-append"], "hosts": ["*"],
            "transport": {"kind": "subprocess-json", "argv": [
                sys.executable, str(ROOT / "run.py"), "--home", str(self.work / "fabric-home"),
                "--workspace", "{workspace}", "bus-stage"]},
        }], {"opencode": {"rank": bus.carrier_rank("jev-context-fabric", "opencode"), "api": "v1"}})

    def run_chain(self, **kwargs):
        return bus.run_chain("opencode", self.messages, session="s1",
                             workspace=str(self.workspace), goal="continue the fixture task",
                             api="v1", **kwargs)

    def test_rank_table_settles_the_contested_host(self):
        self.assertEqual(bus.carrier_of("opencode"), "jev-context-fabric")
        self.assertEqual(bus.carrier_of("pi"), "jev-prune-kit")
        self.assertEqual(bus.carrier_of("hermes"), "jev-prune-kit")

    def test_both_real_stages_run_in_priority_order(self):
        self.assertEqual([s["name"] for s in bus.stages_for("opencode")],
                         ["jev-prune.dedup@opencode", "jev-context.view"])

    def test_dedup_substitutes_a_duplicate_body_without_changing_length(self):
        out, notes, _ = self.run_chain()
        self.assertEqual(len(out), len(self.messages))
        text = self.fixtures.TEXT
        self.assertNotIn(text, json.dumps(out[2]), "the older duplicate read body must be gone")
        self.assertIn(text, json.dumps(out[4]), "the retained copy must keep its full text")
        self.assertTrue(any(n.get("action", "").startswith("duplicate read") for n in notes))

    def test_neither_stage_reports_a_failure(self):
        _, notes, _ = self.run_chain()
        unexpected = [n for n in notes if n.get("action") in ("passthrough", "chain-refused", "skipped")
                      and "no approved" not in n.get("detail", "")]
        self.assertEqual(unexpected, [], f"a stage failed open: {unexpected}")

    def test_upstream_dedup_does_not_rekey_the_prose_the_other_stage_owns(self):
        # The whole reason dedup is ordered first. If this breaks, every approved active
        # view silently stops applying the moment a read is deduplicated.
        out, _, _ = self.run_chain()
        before = [message_key(m, i) for i, m in enumerate(self.messages)]
        after = [message_key(m, i) for i, m in enumerate(out)]
        prose = [i for i, m in enumerate(self.messages)
                 if m.get("info", {}).get("role") == "assistant" and m["parts"][0].get("type") == "text"]
        self.assertGreater(len(prose), 0)
        for i in prose:
            self.assertEqual(before[i], after[i], f"prose message {i} was re-keyed by dedup")
        self.assertTrue(any(before[i] != after[i] for i in range(len(before))),
                        "dedup must actually have changed something")

    def test_evidence_is_appended_only_when_the_carrier_accepts_it(self):
        _, _, appends = self.run_chain()
        self.assertTrue(all(a.startswith("[JEV_CONTEXT_EVIDENCE_V1]") for a in appends))
        _, _, none = self.run_chain(accepts_system_append=False)
        self.assertEqual(none, [], "a stage must not return an append the carrier refused")

    def test_plan_previews_both_packages_and_mutates_nothing(self):
        out, notes, _ = self.run_chain(op="plan")
        self.assertEqual(out, self.messages)
        packages = {n["stage"].split(".")[0] for n in notes if "stage" in n}
        self.assertIn("jev-prune", packages)
        self.assertIn("jev-context", packages)

    def test_a_dead_stage_leaves_the_other_working(self):
        registry = bus.load()
        for entry in registry["stages"]:
            if entry["package"] == "jev-prune-kit":
                entry["transport"]["argv"] = [sys.executable, "-c", "raise SystemExit(3)"]
        bus.atomic_write(bus.registry_path(), bus.dumps(registry).encode())
        out, notes, _ = bus.run_chain("opencode", self.messages, session="s1",
                                      workspace=str(self.workspace), api="v1")
        self.assertIn(self.fixtures.TEXT, json.dumps(out[2]), "the failed stage must change nothing")
        self.assertTrue(any(n["action"] == "passthrough" for n in notes))
        self.assertTrue(any(n.get("action") == "evidence appended" for n in notes),
                        "the healthy stage must still have run")


if __name__ == "__main__":
    unittest.main()
