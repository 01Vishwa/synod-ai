import pytest
from app.orchestration.nodes.dashboard_builder_node import validate_dashboard_spec

def test_dashboard_spec_rejects_unknown_component():
    """
    PRD §11.3, §14: json-render catalog is Zod-validated.
    An unknown component type must fail validation server-side.
    """
    malformed_spec = {
        "root": "widget_1",
        "elements": {
            "widget_1": {
                "component": "UnknownWidget",
                "props": {}
            }
        }
    }

    is_valid, errors = validate_dashboard_spec(malformed_spec)

    assert not is_valid, "Spec with unknown component should be rejected"
    assert any("Unknown component 'UnknownWidget'" in err for err in errors), \
        "Error message should mention unknown component"


def test_dashboard_spec_rejects_unregistered_props():
    """
    PRD §11.3, §14: json-render catalog is Zod-validated.
    Props not in the schema (like an injected 'color' or 'style' prop)
    must fail validation server-side.

    NOTE: This test was previously VACUOUS — Pydantic's default behaviour
    is extra='ignore', which silently discarded 'color' and reported
    is_valid=True, so the `assert not is_valid` line would always FAIL
    (i.e. the test incorrectly asserted that something was rejected when
    it was actually being silently accepted).

    Fix (PRD §14): All _*Props models now carry:
        model_config = ConfigDict(extra='forbid')
    so any extra prop (e.g. 'color') raises a Pydantic ValidationError,
    and this test now correctly verifies the fail-closed safety property.
    """
    malformed_spec = {
        "root": "metric_1",
        "elements": {
            "metric_1": {
                "component": "MetricCard",
                "props": {
                    "label": "Test Metric",
                    "value": 100,
                    "color": "red",  # NOT an allowed prop — must be rejected
                }
            }
        }
    }

    is_valid, errors = validate_dashboard_spec(malformed_spec)

    assert not is_valid, (
        "Spec with an unregistered prop ('color') must be rejected server-side. "
        f"Validation unexpectedly passed. Errors list: {errors}"
    )
    assert any("color" in err or "extra" in err.lower() for err in errors), (
        f"Error message should reference the forbidden 'color' prop. Got: {errors}"
    )


def test_dashboard_spec_accepts_valid_metric_card():
    """
    Regression: a valid MetricCard spec must continue to pass validation.
    """
    valid_spec = {
        "root": "metric_1",
        "elements": {
            "metric_1": {
                "component": "MetricCard",
                "props": {
                    "label": "Total Cost",
                    "value": 0.0042,
                    "unit": "USD",
                    "description": "Accumulated session cost",
                }
            }
        }
    }

    is_valid, errors = validate_dashboard_spec(valid_spec)

    assert is_valid, f"Valid MetricCard spec should pass. Errors: {errors}"
    assert errors == []
