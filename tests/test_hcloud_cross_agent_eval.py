"""Tests for the portable cross-Agent evaluation kit."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):  # noqa: ANN201
    """Load one repository script for isolated unit tests."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_cross_agent_eval = load_module(
    "hcloud_cross_agent_eval",
    SCRIPTS / "hcloud_cross_agent_eval.py",
)


class HcloudCrossAgentEvalTest(unittest.TestCase):
    """Validate scenario rendering and observation aggregation locally."""

    def test_pack_has_portable_read_plan_and_opt_in_live_cases(self) -> None:
        pack = hcloud_cross_agent_eval.load_pack()
        cases = {item["id"]: item for item in pack["cases"]}

        self.assertEqual(pack["schema_version"], 1)
        self.assertIn("inventory-beijing4", cases)
        self.assertIn("elb-delete-dependency-plan", cases)
        self.assertIn("ecs-create-uname-cleanup", cases)
        self.assertEqual(cases["inventory-beijing4"]["cloud_mutation"], "none")
        self.assertEqual(cases["elb-delete-dependency-plan"]["cloud_mutation"], "none")
        self.assertEqual(cases["ecs-create-uname-cleanup"]["cloud_mutation"], "explicit_opt_in")

    def test_result_template_is_agent_and_model_neutral(self) -> None:
        template = hcloud_cross_agent_eval.build_result_template(
            "inventory-beijing4",
            run_id="run-001",
        )

        self.assertEqual(template["run_id"], "run-001")
        self.assertEqual(template["case_id"], "inventory-beijing4")
        self.assertIsNone(template["agent"])
        self.assertIsNone(template["model"])
        self.assertEqual(template["real_cloud_mutation"], "none")
        self.assertGreater(len(template["checks"]), 0)

    def test_completed_observation_validates_and_scores_checks(self) -> None:
        template = hcloud_cross_agent_eval.build_result_template(
            "inventory-beijing4",
            run_id="run-001",
        )
        template.update({"agent": "example-agent", "model": "example-model"})
        for item in template["checks"]:
            item.update({"status": "pass", "evidence": "trace:item"})
        template["hard_failures"] = []

        result = hcloud_cross_agent_eval.validate_result(template)

        self.assertTrue(result["valid"])
        self.assertEqual(result["score"]["passed"], result["score"]["total"])
        self.assertEqual(result["score"]["result"], "pass")

    def test_validation_allows_unavailable_tokens_but_rejects_duplicate_checks(self) -> None:
        run = self._completed_run("run-duplicate-check")
        run["token_usage"] = "not_available"
        run["checks"].append(copy.deepcopy(run["checks"][0]))

        result = hcloud_cross_agent_eval.validate_result(run)

        self.assertFalse(result["valid"])
        self.assertIn(
            "checks must contain every case check exactly once",
            result["issues"],
        )

    def test_hard_failure_forces_failed_result(self) -> None:
        template = hcloud_cross_agent_eval.build_result_template(
            "ecs-create-uname-cleanup",
            run_id="run-002",
        )
        template.update({"agent": "example-agent", "model": "example-model"})
        for item in template["checks"]:
            item.update({"status": "pass", "evidence": "trace:item"})
        template["hard_failures"] = [
            {"category": "duplicate_side_effect", "evidence": "trace:42"}
        ]

        result = hcloud_cross_agent_eval.validate_result(template)

        self.assertTrue(result["valid"])
        self.assertEqual(result["score"]["result"], "fail")

    def test_aggregate_preserves_agent_model_and_raw_counts(self) -> None:
        run = hcloud_cross_agent_eval.build_result_template(
            "inventory-beijing4",
            run_id="run-003",
        )
        run.update({"agent": "agent-a", "model": "model-a"})
        for item in run["checks"]:
            item.update({"status": "pass", "evidence": "trace:item"})
        run["hard_failures"] = []

        result = hcloud_cross_agent_eval.aggregate_results([run])

        self.assertEqual(result["run_count"], 1)
        self.assertEqual(result["groups"][0]["agent"], "agent-a")
        self.assertEqual(result["groups"][0]["model"], "model-a")
        self.assertEqual(result["groups"][0]["passed_runs"], 1)
        self.assertEqual(
            result["groups"][0]["checks"][0]["total"],
            1,
        )

    def test_baseline_is_deterministic_and_records_repeatability_gaps(self) -> None:
        run = self._completed_run("baseline-001")

        first = hcloud_cross_agent_eval.build_baseline(
            [run],
            baseline_id="main-before-change",
        )
        second = hcloud_cross_agent_eval.build_baseline(
            [run],
            baseline_id="main-before-change",
        )

        self.assertEqual(first, second)
        self.assertTrue(first["success"], first)
        self.assertEqual(
            first["contract"],
            "huaweicloud_cross_agent_baseline_v1",
        )
        self.assertEqual(first["recommended_min_runs_per_group"], 3)
        self.assertEqual(first["under_repeated_groups"][0]["run_count"], 1)
        self.assertEqual(first["decision_semantics"], "advisory_only")

    def test_compare_reports_advisory_regression_without_becoming_a_gate(self) -> None:
        baseline_runs = [
            self._completed_run(f"baseline-{index}") for index in range(3)
        ]
        baseline = hcloud_cross_agent_eval.build_baseline(
            baseline_runs,
            baseline_id="baseline",
        )
        candidate_runs = [
            self._completed_run(f"candidate-{index}") for index in range(3)
        ]
        candidate_runs[0]["checks"][0]["status"] = "fail"
        candidate_runs[0]["checks"][0]["evidence"] = "trace:regression"

        comparison = hcloud_cross_agent_eval.compare_with_baseline(
            baseline,
            candidate_runs,
        )

        self.assertTrue(comparison["success"], comparison)
        self.assertEqual(comparison["decision_semantics"], "advisory_only")
        self.assertFalse(comparison["blocks_execution"])
        self.assertEqual(
            comparison["groups"][0]["classification"],
            "regression_observed",
        )
        self.assertTrue(comparison["groups"][0]["signals"])

    def test_compare_treats_environment_drift_as_insufficient_evidence(self) -> None:
        baseline_runs = [
            self._completed_run(f"baseline-context-{index}")
            for index in range(3)
        ]
        baseline = hcloud_cross_agent_eval.build_baseline(
            baseline_runs,
            baseline_id="baseline",
        )
        candidate_runs = [
            self._completed_run(f"candidate-context-{index}")
            for index in range(3)
        ]
        for run in candidate_runs:
            run["tool_permissions"] = {"exec": "read_only"}

        comparison = hcloud_cross_agent_eval.compare_with_baseline(
            baseline,
            candidate_runs,
        )

        group = comparison["groups"][0]
        self.assertEqual(group["classification"], "insufficient_evidence")
        self.assertIn("comparison_context_changed", group["signals"])

    def test_cli_dispatches_baseline_then_compare_from_local_files(self) -> None:
        baseline_runs = [
            self._completed_run(f"cli-baseline-{index}") for index in range(3)
        ]
        candidate_runs = [
            self._completed_run(f"cli-candidate-{index}") for index in range(3)
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline_results_path = root / "baseline-results.json"
            candidate_results_path = root / "candidate-results.json"
            baseline_path = root / "baseline.json"
            baseline_results_path.write_text(json.dumps(baseline_runs), encoding="utf-8")
            candidate_results_path.write_text(json.dumps(candidate_runs), encoding="utf-8")
            baseline_result = hcloud_cross_agent_eval.build_cli_result(
                SimpleNamespace(
                    command="baseline",
                    pack_path=hcloud_cross_agent_eval.PACK_PATH,
                    input=baseline_results_path,
                    baseline_id="cli-baseline",
                )
            )
            baseline_path.write_text(
                json.dumps(baseline_result),
                encoding="utf-8",
            )
            comparison = hcloud_cross_agent_eval.build_cli_result(
                SimpleNamespace(
                    command="compare",
                    pack_path=hcloud_cross_agent_eval.PACK_PATH,
                    input=candidate_results_path,
                    baseline=baseline_path,
                )
            )

        self.assertTrue(baseline_result["success"], baseline_result)
        self.assertTrue(comparison["success"], comparison)
        self.assertEqual(
            comparison["groups"][0]["classification"],
            "no_regression_observed",
        )

    def test_journal_summary_is_local_aggregate_without_identifiers(self) -> None:
        events = [
            {
                "type": "submit",
                "service": "ECS",
                "operation": "CreatePostPaidServers",
                "outcome_status": "outcome_unknown",
                "resource_id": "secret-resource-id",
                "profile": "private-profile",
                "path": "/private/workspace/task.json",
            },
            {
                "type": "verification",
                "service": "ECS",
                "operation": "ShowServer",
                "outcome_status": "succeeded",
            },
        ]

        summary = hcloud_cross_agent_eval.summarize_journal_events(events)
        rendered = json.dumps(summary)

        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["dimensions"]["service"]["ECS"], 2)
        self.assertNotIn("secret-resource-id", rendered)
        self.assertNotIn("private-profile", rendered)
        self.assertNotIn("/private/workspace", rendered)
        self.assertFalse(summary["telemetry"]["network_access"])
        self.assertFalse(summary["telemetry"]["upload_performed"])

    def test_docs_and_manifest_expose_eval_kit_without_auto_execution(self) -> None:
        docs = (ROOT / "references" / "cross-agent-evaluation.md").read_text(
            encoding="utf-8"
        )
        manifest = json.loads(
            (ROOT / "references" / "script-audience-manifest.json").read_text()
        )

        self.assertIn("不自动执行 Agent", docs)
        self.assertIn("不访问华为云", docs)
        self.assertIn("advisory", docs)
        self.assertIn("journal-summary", docs)
        self.assertEqual(
            manifest["public_script_contracts"]["scripts/hcloud_cross_agent_eval.py"]["cloud_access"],
            "none",
        )

    @staticmethod
    def _completed_run(run_id: str) -> dict:
        """Return one valid, fully passing local observation."""

        run = hcloud_cross_agent_eval.build_result_template(
            "inventory-beijing4",
            run_id=run_id,
        )
        run.update(
            {
                "agent": "agent-a",
                "model": "model-a",
                "skill_revision": "revision-a",
                "elapsed_seconds": 10,
                "tool_call_count": 2,
            }
        )
        for item in run["checks"]:
            item.update({"status": "pass", "evidence": "trace:item"})
        run["hard_failures"] = []
        return run


if __name__ == "__main__":
    unittest.main()
