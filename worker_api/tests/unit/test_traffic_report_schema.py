from app.schemas.end_user import TrafficReportRequest


def test_v1_payload_still_valid_with_defaults():
    r = TrafficReportRequest(
        username="u",
        protocol="vless",
        region="CH",
        bytes_in=1,
        bytes_out=2,
        instance_ip="unknown",
    )
    assert r.report_version == 1
    assert r.cumulative_in is None


def test_v2_payload_carries_cumulative_fields():
    r = TrafficReportRequest(
        username="u",
        protocol="vless",
        region="CH",
        bytes_in=0,
        bytes_out=0,
        instance_ip="unknown",
        report_version=2,
        cumulative_in=100,
        cumulative_out=200,
        boot_id="boot-x",
        instance_id="inst-9",
    )
    assert r.report_version == 2
    assert r.cumulative_in == 100 and r.cumulative_out == 200
    assert r.boot_id == "boot-x" and r.instance_id == "inst-9"
