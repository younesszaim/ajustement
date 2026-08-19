"""The complete Streamlit-to-FastAPI communication boundary."""

from __future__ import annotations

import httpx


class ApiError(Exception):
    """User-displayable failure returned by or while contacting FastAPI."""

    pass


class AdjustmentApiClient:
    """Small typed-by-convention wrapper around the LiMon HTTP routes."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        """Store the API root and a common request timeout."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs):
        """Send one request and expose a clean message instead of HTTPX errors."""
        try:
            response = httpx.request(
                method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            try:
                message = exc.response.json().get("detail", exc.response.text)
            except ValueError:
                message = exc.response.text
            raise ApiError(message or f"API returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"Cannot reach the LiMon API at {self.base_url}: {exc}") from exc

    def asofdates(self):
        """Fetch values used by the as-of calendar."""
        return self._request("GET", "/contexts/asofdates")["items"]

    def versions(self, asofdate):
        """Fetch version choices after an as-of date is selected."""
        return self._request("GET", "/contexts/versions", params={"asofdate": asofdate})["items"]

    def fo_systems(self, asofdate, version):
        """Fetch FO-system choices for the selected output snapshot."""
        return self._request(
            "GET", "/contexts/fo-systems", params={"asofdate": asofdate, "version": version}
        )["items"]

    def trades(self, context, search="", limit=500):
        """Fetch a bounded set of active rows; AG Grid filters this subset."""
        return self._request(
            "GET",
            "/trades",
            params={**context.__dict__, "search": search, "limit": limit},
        )["items"]

    @staticmethod
    def adjustment_body(context, draft):
        """Serialize domain dataclasses into the API's JSON shape.

        Example: an ``AdjustmentDraft`` changing exposure class produces a
        ``changes`` object such as ``{"exposure_class": "FINANCIAL"}``.
        """
        return {
            "context": context.__dict__,
            "source_output_id": draft.source_output_id,
            "new_amount": draft.new_amount,
            "reason": draft.reason,
            "idempotency_key": draft.idempotency_key,
            "changes": draft.changes,
        }

    def preview(self, context, draft):
        """Request a read-only original/reversal/adjusted calculation."""
        return self._request(
            "POST", "/adjustments/preview", json=self.adjustment_body(context, draft)
        )

    def start_preview(self, context, draft):
        """Start a background preview and return its initial job snapshot."""
        return self._request(
            "POST", "/adjustments/preview-jobs", json=self.adjustment_body(context, draft)
        )

    def preview_status(self, job_id: str):
        """Poll current calculation stage and retrieve the final result."""
        return self._request("GET", f"/adjustments/preview-jobs/{job_id}")

    def commit(self, context, draft):
        """Persist a previously reviewable adjustment intention."""
        return self._request(
            "POST", "/adjustments/commit", json=self.adjustment_body(context, draft)
        )

    def adjustments(self, limit=1000):
        """Fetch operation metadata for the Adjustment Register."""
        return self._request("GET", "/adjustments", params={"limit": limit})["items"]

    def revert(self, operation_id: str, reason: str, idempotency_key: str):
        """Request an append-only revert of one committed replacement."""
        return self._request(
            "POST",
            f"/adjustments/{operation_id}/revert",
            json={"reason": reason, "idempotency_key": idempotency_key},
        )
