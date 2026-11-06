"""Nov 5 2026: Water Mitigation and Mold Remediation got new JobNimbus statuses and hid the roofing ones.
Mold's last work status joins the Primary Completed tab; water's drying statuses are not pulled (water jobs are not built)."""
import pytest

from backend.services import jobnimbus as JN


def test_a_mold_job_waiting_on_its_clearance_test_lands_in_primary_completed_not_archived():
    assert "Waiting on Clearance Test" in JN.TRACKED_JN_STATUSES  # pulled by the sync, so never archived
    mapped = JN.map_jn_job_to_model({"jnid": "abc", "status_name": "Waiting on Clearance Test", "name": "Pat Doe - J-1"})
    assert mapped["bucket"] == "primary_completed"


@pytest.mark.parametrize("name", ["Drying - Equipment On Site", "Dry Standard Met - Pull Equipment",
                                  "Scope and Paperwork Review", "Waiting on Carrier Review", "Report and Proposal Sent"])
def test_water_drying_and_paperwork_statuses_are_not_pulled_into_the_scheduler(name):
    assert name not in JN.TRACKED_JN_STATUSES
