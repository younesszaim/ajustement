"""Pure helpers for keeping a Streamlit draft and its retry key consistent."""

from __future__ import annotations

import json


def draft_signature(
    *, context, source_output_id: str, new_amount: float,
    changes: dict[str, object], reason: str,
) -> str:
    """Return a stable identity for the complete adjustment intention.

    The same draft keeps its retry key after a timeout. Changing any committed
    input changes this signature and therefore requires a new retry key.
    """
    intention = {
        "context": {
            "asofdate": str(context.asofdate),
            "version": str(context.version),
            "fo_system": str(context.fo_system),
            "leg_flag": int(context.leg_flag),
        },
        "source_output_id": str(source_output_id),
        "new_amount": float(new_amount),
        "changes": changes,
        "reason": reason.strip(),
    }
    return json.dumps(intention, sort_keys=True, separators=(",", ":"), default=str)
