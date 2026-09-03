import json

from app.stream_writer import build_fields, stream_key


def test_stream_key_prefixes_topic():
    assert stream_key("a/b/_informative") == "live:a/b/_informative"


def test_build_fields_serializes_payload_as_json_string():
    fields = build_fields({"Gen_RPM_Avg": 1342.1}, "2026-09-03T10:00:00+00:00")
    assert fields["time"] == "2026-09-03T10:00:00+00:00"
    assert json.loads(fields["payload"]) == {"Gen_RPM_Avg": 1342.1}
