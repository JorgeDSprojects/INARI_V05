from app.catalog import SignalDefinition, diff_definitions, extract_definitions


def test_extract_raw_signal_definitions():
    payload = {
        "schema_version": "1.0.0",
        "signals": {
            "Gen_RPM_Avg": {
                "unit": "RPM", "data_type": "float", "range_min": 0, "range_max": 1700,
                "thresholds": {"warning_high": 1400, "alarm_high": 1500},
            },
        },
    }
    definitions = extract_definitions(payload)
    assert definitions == [
        SignalDefinition(
            signal_key="Gen_RPM_Avg", signal_type="raw", unit="RPM", data_type="float",
            range_min=0, range_max=1700, thresholds={"warning_high": 1400, "alarm_high": 1500},
            description=None, source_version="1.0.0",
        )
    ]


def test_extract_kpi_definitions():
    payload = {
        "analytical": {
            "version": 2,
            "kpis": {
                "phase_imbalance_max_delta_c": {
                    "unit": "°C", "thresholds": {"warning": 5, "alarm": 10},
                    "description": "Max difference between any two phase temperatures",
                },
            },
        },
    }
    definitions = extract_definitions(payload)
    assert definitions == [
        SignalDefinition(
            signal_key="phase_imbalance_max_delta_c", signal_type="kpi", unit="°C", data_type=None,
            range_min=None, range_max=None, thresholds={"warning": 5, "alarm": 10},
            description="Max difference between any two phase temperatures", source_version="2",
        )
    ]


def test_missing_sections_yield_no_definitions():
    assert extract_definitions({"schema_version": "1.0.0"}) == []


def test_malformed_signal_entry_is_skipped_not_raised():
    payload = {"signals": {"Gen_RPM_Avg": "not an object"}}
    assert extract_definitions(payload) == []


def test_diff_flags_brand_new_signal():
    incoming = [SignalDefinition(signal_key="a", signal_type="raw", unit="RPM")]
    assert diff_definitions({}, incoming) == incoming


def test_diff_ignores_unchanged_signal():
    definition = SignalDefinition(signal_key="a", signal_type="raw", unit="RPM")
    assert diff_definitions({"a": definition}, [definition]) == []


def test_diff_flags_changed_threshold():
    old = SignalDefinition(signal_key="a", signal_type="raw", unit="RPM", thresholds={"warning_high": 1400})
    new = SignalDefinition(signal_key="a", signal_type="raw", unit="RPM", thresholds={"warning_high": 1450})
    assert diff_definitions({"a": old}, [new]) == [new]


def test_diff_flags_changed_range():
    old = SignalDefinition(signal_key="a", signal_type="raw", range_min=0, range_max=1700)
    new = SignalDefinition(signal_key="a", signal_type="raw", range_min=0, range_max=1800)
    assert diff_definitions({"a": old}, [new]) == [new]
