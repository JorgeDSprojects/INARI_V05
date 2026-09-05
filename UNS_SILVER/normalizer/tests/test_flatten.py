from app.flatten import FlatEvent, FlatValue, flatten_payload


def test_top_level_scalars_become_values():
    result = flatten_payload({"Gen_RPM_Avg": 1249.0, "status": "WARNING"}, max_depth=6, max_keys=500)
    assert FlatValue(path="Gen_RPM_Avg", value_numeric=1249.0, value_text=None) in result.values
    assert FlatValue(path="status", value_numeric=None, value_text="WARNING") in result.values
    assert result.events == []
    assert result.truncated is False


def test_top_level_timestamp_key_is_skipped():
    result = flatten_payload({"timestamp": "2026-09-05T13:52:54.269Z", "status": "OK"}, max_depth=6, max_keys=500)
    paths = [v.path for v in result.values]
    assert "timestamp" not in paths
    assert "status" in paths


def test_nested_scalar_becomes_dot_path_value():
    result = flatten_payload({"fleet_health_score": {"value": 0.88, "confidence": 0.85}}, max_depth=6, max_keys=500)
    assert FlatValue(path="fleet_health_score.value", value_numeric=0.88, value_text=None) in result.values
    assert FlatValue(path="fleet_health_score.confidence", value_numeric=0.85, value_text=None) in result.values


def test_array_of_scalars_becomes_one_json_text_value():
    result = flatten_payload({"escalation_timeout_minutes": [15, 60, 240]}, max_depth=6, max_keys=500)
    assert result.values == [FlatValue(path="escalation_timeout_minutes", value_numeric=None, value_text="[15, 60, 240]")]
    assert result.events == []


def test_array_of_objects_becomes_one_event_per_element():
    payload = {
        "status": "WARNING",
        "alarms": [
            {"signal": "Gen_RPM_Avg", "severity": "WARNING", "current_value": 1427.4, "threshold_violated": 1400},
        ],
    }
    result = flatten_payload(payload, max_depth=6, max_keys=500)
    assert result.events == [
        FlatEvent(
            event_key="alarms",
            payload={"signal": "Gen_RPM_Avg", "severity": "WARNING", "current_value": 1427.4, "threshold_violated": 1400},
        )
    ]
    assert FlatValue(path="status", value_numeric=None, value_text="WARNING") in result.values


def test_boolean_is_stored_as_text():
    result = flatten_payload({"has_slip_ring": True}, max_depth=6, max_keys=500)
    assert result.values == [FlatValue(path="has_slip_ring", value_numeric=None, value_text="True")]


def test_null_is_stored_as_value_with_no_numeric_or_text():
    result = flatten_payload({"note": None}, max_depth=6, max_keys=500)
    assert result.values == [FlatValue(path="note", value_numeric=None, value_text=None)]


def test_depth_cap_truncates_and_flags():
    deeply_nested = {"a": {"b": {"c": {"d": 1}}}}
    result = flatten_payload(deeply_nested, max_depth=2, max_keys=500)
    assert result.truncated is True
    assert result.values == []


def test_key_count_cap_truncates_and_flags():
    payload = {f"key_{i}": i for i in range(10)}
    result = flatten_payload(payload, max_depth=6, max_keys=5)
    assert len(result.values) == 5
    assert result.truncated is True


def test_non_dict_payload_returns_empty_result():
    result = flatten_payload("not a dict", max_depth=6, max_keys=500)
    assert result.values == []
    assert result.events == []
    assert result.truncated is False


def test_empty_array_produces_nothing():
    result = flatten_payload({"failure_events": []}, max_depth=6, max_keys=500)
    assert result.values == []
    assert result.events == []
