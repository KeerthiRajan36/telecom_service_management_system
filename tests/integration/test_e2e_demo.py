"""Runs the mandatory end-to-end demo flow exactly as it is shown to reviewers."""
from scripts.demo_flow import run_demo


def test_mandatory_end_to_end_flow(client):
    lines = []
    result = run_demo(client, log=lines.append)
    assert "Demo flow completed successfully." in lines[-1]
    assert result["ticket_final"]["status"] == "resolved"
    assert result["outage_final"]["status"] == "resolved"
    assert {"network_outage", "service_restoration", "ticket_assignment"} <= set(result["notification_types"])
    assert result["dashboard"]["open_network_outages"] == 0 and result["audit_total"] > 15
