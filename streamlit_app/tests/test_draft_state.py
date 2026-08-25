from streamlit_app.draft_state import draft_signature
from streamlit_app.models import Context


def test_signature_is_stable_for_the_same_complete_draft():
    context = Context("2026-08-06", "v1", "Murex", 0)
    first = draft_signature(
        context=context, source_output_id="ROW-1", new_amount=250,
        changes={"exposure_class": "CORPORATE", "reporting_line_lcr": "RL-1"},
        reason="  Correction  ",
    )
    retry = draft_signature(
        context=context, source_output_id="ROW-1", new_amount=250.0,
        changes={"reporting_line_lcr": "RL-1", "exposure_class": "CORPORATE"},
        reason="Correction",
    )
    assert first == retry


def test_signature_changes_when_any_intention_input_changes():
    context = Context("2026-08-06", "v1", "Murex", 0)
    common = {
        "context": context, "source_output_id": "ROW-1", "new_amount": 250.0,
        "changes": {"exposure_class": "CORPORATE"}, "reason": "Correction",
    }
    baseline = draft_signature(**common)
    variants = [
        {**common, "source_output_id": "ROW-2"},
        {**common, "new_amount": 300.0},
        {**common, "changes": {"exposure_class": "SOVEREIGN"}},
        {**common, "reason": "Another reason"},
        {**common, "context": Context("2026-08-06", "v2", "Murex", 0)},
    ]
    assert all(draft_signature(**variant) != baseline for variant in variants)
