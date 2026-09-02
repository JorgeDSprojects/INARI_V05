from datetime import datetime, timezone

from app.normalize import Reading, parse_message

ARRIVAL = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_single_object_without_timestamp_uses_arrival_time():
    raw = b'{"voltage_v": 690, "manufacturer": "Vestas"}'
    readings = parse_message(raw, ARRIVAL)
    assert readings == [
        Reading(time=ARRIVAL, payload={"voltage_v": 690, "manufacturer": "Vestas"}, raw_payload=None)
    ]


def test_single_object_with_valid_timestamp_uses_payload_timestamp():
    raw = b'{"timestamp": "2026-09-02T13:23:24.902Z", "Gen_RPM_Avg": 1008.9}'
    readings = parse_message(raw, ARRIVAL)
    assert len(readings) == 1
    assert readings[0].time == datetime(2026, 9, 2, 13, 23, 24, 902000, tzinfo=timezone.utc)
    assert readings[0].payload["Gen_RPM_Avg"] == 1008.9


def test_list_of_objects_splits_into_multiple_readings():
    raw = (
        b'[{"timestamp": "2026-09-02T13:20:16.748Z", "Gen_RPM_Avg": 1572.5},'
        b' {"timestamp": "2026-09-02T13:20:17.748Z", "Gen_RPM_Avg": 1580.1}]'
    )
    readings = parse_message(raw, ARRIVAL)
    assert len(readings) == 2
    assert readings[0].time == datetime(2026, 9, 2, 13, 20, 16, 748000, tzinfo=timezone.utc)
    assert readings[1].time == datetime(2026, 9, 2, 13, 20, 17, 748000, tzinfo=timezone.utc)


def test_invalid_json_falls_back_to_raw_payload():
    raw = b"not json at all"
    readings = parse_message(raw, ARRIVAL)
    assert readings == [Reading(time=ARRIVAL, payload=None, raw_payload="not json at all")]


def test_empty_payload_returns_single_null_reading():
    readings = parse_message(b"", ARRIVAL)
    assert readings == [Reading(time=ARRIVAL, payload=None, raw_payload=None)]


def test_object_with_unparseable_timestamp_falls_back_to_arrival_time():
    raw = b'{"timestamp": "not-a-date", "value": 1}'
    readings = parse_message(raw, ARRIVAL)
    assert readings[0].time == ARRIVAL
    assert readings[0].payload["timestamp"] == "not-a-date"
