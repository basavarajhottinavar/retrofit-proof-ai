import unittest
from unittest.mock import patch

from pydantic import ValidationError

from main import AssessmentRequest, assess_request


class AssessmentTests(unittest.TestCase):
    def test_incomplete_intake_lists_missing_information(self):
        response = assess_request(
            AssessmentRequest(
                project_name="Demo packaging line",
                application="Case packer",
            )
        )

        self.assertEqual(response.status, "information_incomplete")
        self.assertIn("Operating pressure", response.missing_information)
        self.assertIn("As-built I/O list", response.missing_information)
        self.assertTrue(response.requires_engineer_review)
        self.assertEqual(response.bom_status, "not_generated")

    def test_complete_intake_is_still_for_engineer_review(self):
        response = assess_request(
            AssessmentRequest(
                project_name="Demo packaging line",
                application="Case packer",
                operating_pressure_bar=6,
                target_cycle_rate_per_min=30,
                diagram_available=True,
                io_list_available=True,
                observed_components=["V1, valve manifold"],
                current_quote_hours=10,
                estimated_quote_hours=7,
                engineering_hourly_cost_inr=1000,
            )
        )

        self.assertEqual(response.status, "awaiting_engineer_review")
        self.assertTrue(response.requires_engineer_review)
        self.assertEqual(response.roi_estimate.engineering_hours_saved, 3)
        self.assertEqual(response.roi_estimate.estimated_cost_savings_inr, 3000)
        self.assertEqual(response.bom_status, "not_generated")

    def test_non_positive_pressure_is_rejected(self):
        with self.assertRaises(ValidationError):
            AssessmentRequest(
                project_name="Demo",
                application="Case packer",
                operating_pressure_bar=0,
            )

    def test_part_numbers_and_names_both_reach_project_crosswalk_lookup(self):
        expected_lookups = [
            {
                "query": "KQ2T16-00A",
                "status": "matched",
                "matches_truncated": False,
                "matches": [],
                "review_notice": "Exact local crosswalk lookup.",
            }
        ]
        with patch("main.lookup_project_component_names", return_value=expected_lookups) as lookup:
            response = assess_request(
                AssessmentRequest(
                    project_name="Project RetrofitProof AI",
                    application="Pneumatic component lookup",
                    legacy_part_numbers=["KQ2T16-00A"],
                    legacy_component_names=["Push-in T-connector"],
                )
            )

        lookup.assert_called_once_with(["KQ2T16-00A", "Push-in T-connector"])
        self.assertEqual(
            [item.model_dump() for item in response.component_name_lookups],
            expected_lookups,
        )


if __name__ == "__main__":
    unittest.main()