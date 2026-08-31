from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_aquagold_outbound_messages_are_filtered_before_intake():
    code = source("bale_inbox_guard.py")
    assert 'sender.get("is_bot")' in code
    assert "❌ لغو کار AquaGold" in code
    assert "📊 گزارش پایان کار" in code
    assert '"ignored": "aquagold_outbound"' in code


def test_existing_self_report_ghosts_are_only_cleaned_before_core_service():
    code = source("bale_inbox_guard.py")
    assert "status in ('new','review')" in code
    assert "service_visit_id is null" in code
    assert "delete from bale_jobs" in code


def test_discard_endpoint_refuses_completed_service_jobs():
    code = source("bale_inbox_guard.py")
    assert '@app_v3.app.delete("/api/bale/jobs/<job_id>")' in code
    assert 'job.get("status") == "completed"' in code
    assert 'job.get("service_visit_id")' in code
    assert "deleteBaleJob" in code
    assert "bale-hard-delete" in code
