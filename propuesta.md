El siguiente paso es que quiero implementar sistemas como LLMs y agentes que interactuen con las señales en tiempo real y con las del historian.
La idea es poder hacer operaciones por ejemplo, poder ayudarme a generar un dashboard mediante un chatbot, o por ejemplo poder consultar valores de manera directa.

Plantea que voy a tener un sistema con una escala de topics individuales de mas de 1000 topics con frecuencias desde 0,3 seg a 5 segundos
Por esto estaba pensando en añadir sistemas que me permitan hacer los datos bronze a silver, pensaba en un sistema desacoplado 

Piensa que el descriptive y el informational tiene este tipo de informacion 
[uns/v1/GALERNA_ENERGY/SPAIN/GALICIA_COSTA_MORTE/T01/GENERATOR/_descriptive
```

```json
{
  "schema_version": "1.0.0",
  "subsystem_id": "GENERATOR",
  "subsystem_type": "doubly_fed_induction_generator",
  "manufacturer": "Vestas",
  "rated_power_kw": 2000,
  "voltage_v": 690,
  "frequency_hz": 50,
  "pole_pairs": 2,
  "cooling_type": "forced_air",
  "bearing_count": 2,
  "has_slip_ring": true,
  "signals": {
    "Gen_RPM_Max": { "unit": "RPM", "data_type": "float", "range_min": 0, "range_max": 1800, "default_chart": { "type": "time_series", "show_thresholds": false, "recommended_window": "24h" } },
    "Gen_RPM_Min": { "unit": "RPM", "data_type": "float", "range_min": 0, "range_max": 1700, "default_chart": { "type": "time_series", "show_thresholds": false, "recommended_window": "24h" } },
    "Gen_RPM_Avg": { "unit": "RPM", "data_type": "float", "range_min": 0, "range_max": 1700, "default_chart": { "type": "time_series", "show_thresholds": true, "recommended_window": "24h" } },
    "Gen_RPM_Std": { "unit": "RPM", "data_type": "float", "range_min": 0, "range_max": 600, "default_chart": { "type": "time_series", "show_thresholds": false, "recommended_window": "24h" } },
    "Gen_Bear_Temp_Avg": { "unit": "°C", "data_type": "integer", "range_min": 10, "range_max": 100, "default_chart": { "type": "time_series", "show_thresholds": true, "recommended_window": "24h" } },
    "Gen_Bear2_Temp_Avg": { "unit": "°C", "data_type": "integer", "range_min": 10, "range_max": 100, "default_chart": { "type": "time_series", "show_thresholds": true, "recommended_window": "24h" } },
    "Gen_Phase1_Temp_Avg": { "unit": "°C", "data_type": "integer", "range_min": 15, "range_max": 130, "default_chart": { "type": "time_series", "show_thresholds": true, "recommended_window": "24h" } },
    "Gen_Phase2_Temp_Avg": { "unit": "°C", "data_type": "integer", "range_min": 15, "range_max": 130, "default_chart": { "type": "time_series", "show_thresholds": true, "recommended_window": "24h" } },
    "Gen_Phase3_Temp_Avg": { "unit": "°C", "data_type": "integer", "range_min": 15, "range_max": 130, "default_chart": { "type": "time_series", "show_thresholds": true, "recommended_window": "24h" } },
    "Gen_SlipRing_Temp_Avg": { "unit": "°C", "data_type": "integer", "range_min": 10, "range_max": 100, "default_chart": { "type": "time_series", "show_thresholds": true, "recommended_window": "24h" } }
  }
}
```

#### `_informational`

```json
{
  "timestamp": "2016-01-01T00:00:00+00:00",
  "Gen_RPM_Max": 1277.4, "Gen_RPM_Min": 1226.1, "Gen_RPM_Avg": 1249.0, "Gen_RPM_Std": 9.0,
  "Gen_Bear_Temp_Avg": 41, "Gen_Bear2_Temp_Avg": 37,
  "Gen_Phase1_Temp_Avg": 58, "Gen_Phase2_Temp_Avg": 59, "Gen_Phase3_Temp_Avg": 58,
  "Gen_SlipRing_Temp_Avg": 25
}]

Y en el caso del Analytical [`_analytical`

```json
{
  "effective_since": "2016-01-01T00:00:00+00:00",
  "version": 2,
  "thresholds": {
    "Gen_RPM_Avg": { "warning_low": 950, "alarm_low": 900, "warning_high": 1400, "alarm_high": 1500, "unit": "RPM" },
    "Gen_Bear_Temp_Avg": { "warning_high": 65, "alarm_high": 80, "unit": "°C" },
    "Gen_Bear2_Temp_Avg": { "warning_high": 65, "alarm_high": 80, "unit": "°C" },
    "Gen_Phase1_Temp_Avg": { "warning_high": 85, "alarm_high": 100, "unit": "°C" },
    "Gen_Phase2_Temp_Avg": { "warning_high": 85, "alarm_high": 100, "unit": "°C" },
    "Gen_Phase3_Temp_Avg": { "warning_high": 85, "alarm_high": 100, "unit": "°C" },
    "Gen_SlipRing_Temp_Avg": { "warning_high": 70, "alarm_high": 90, "unit": "°C" },
    "phase_imbalance_max_delta_c": { "warning": 5, "alarm": 10, "description": "Max difference between any two phase temperatures" }
  },
  "health_score": { "value": 0.95, "confidence": 0.90, "calculated_at": "2016-01-01T00:00:00+00:00" },
  "failure_events": []
}]
Esto solo cubre la descripcion del caso de uso pero no la señal en si misma, en este caso el KPI
Eres un soluction architect revisa estos planteamientos y abordemos un plan de desarrollo
hazme las pregutnas necesarios para aclarar el funcionamiento



{
  "timestamp": "2026-09-05T13:52:54.269Z",
  "subsystem_id": "GENERATOR",
  "status": "WARNING",
  "active_alarms_count": 1,
  "alarms": [
    {
      "signal": "Gen_RPM_Avg",
      "severity": "WARNING",
      "current_value": 1427.4,
      "threshold_violated": 1400,
      "message": "Advertencia de temperatura/RPM alta"
    }
  ]
}