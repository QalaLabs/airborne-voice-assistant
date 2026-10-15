import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

import config
import main
import piopiy_agent_worker
import precall_manager


class ApiKeyAuthTests(unittest.TestCase):
    PROTECTED = [
        ("post", "/api/calls/dispatch", {"phone": "+919999999999"}),
        ("post", "/api/calls/prefeed", {"phone": "+919999999999"}),
        ("get", "/api/calls/prefeed/+919999999999", None),
        ("post", "/webhooks/new-lead", {"phone": "+919999999999"}),
    ]

    def setUp(self):
        self._orig = config.API_SHARED_SECRET
        self.client = TestClient(main.app)

    def tearDown(self):
        config.API_SHARED_SECRET = self._orig

    def _call(self, method, path, body, headers=None):
        kwargs = {"headers": headers or {}}
        if body is not None:
            kwargs["json"] = body
        return getattr(self.client, method)(path, **kwargs)

    def test_fails_closed_when_secret_unset(self):
        config.API_SHARED_SECRET = ""
        for method, path, body in self.PROTECTED:
            self.assertEqual(self._call(method, path, body).status_code, 503, path)

    def test_rejects_missing_or_wrong_key(self):
        config.API_SHARED_SECRET = "s3cret"
        for method, path, body in self.PROTECTED:
            self.assertEqual(self._call(method, path, body).status_code, 401, path)
            self.assertEqual(
                self._call(method, path, body, {"X-API-Key": "nope"}).status_code, 401, path
            )

    def test_accepts_correct_key_header_and_bearer(self):
        config.API_SHARED_SECRET = "s3cret"
        # GET prefeed for an unknown phone passes auth and returns 404 from the handler.
        for headers in ({"X-API-Key": "s3cret"}, {"Authorization": "Bearer s3cret"}):
            r = self._call("get", "/api/calls/prefeed/+910000000001", None, headers)
            self.assertNotIn(r.status_code, (401, 503))

    def test_public_endpoints_stay_open(self):
        config.API_SHARED_SECRET = "s3cret"
        self.assertEqual(self.client.get("/webhooks/new-lead").status_code, 200)


class TestLeadMatchingTests(unittest.TestCase):
    def test_exact_number_matches_test_lead(self):
        for phone, name in (
            ("+919811817062", "Deepak"),
            ("9910241143", "Aayush"),
            ("916006760151", "Aashirwad"),
        ):
            d = piopiy_agent_worker.build_test_lead_dossier(phone)
            self.assertIsNotNone(d, phone)
            self.assertEqual(d.name, name)

    def test_lookalike_numbers_do_not_match(self):
        for phone in ("+919000007062", "+919876540151", "+919876541143", "+910000000000"):
            self.assertIsNone(piopiy_agent_worker.build_test_lead_dossier(phone), phone)

    def test_context_substrings_do_not_hijack_real_callers(self):
        direction, phone = piopiy_agent_worker.resolve_call_context(
            {
                "from_number": "9876540151",
                "to_number": "917943446755",
                "room_name": "piopiyai_7062_abc",
                "metadata": {"note": "deepak aayush"},
            }
        )
        self.assertEqual(direction, "inbound")
        self.assertEqual(phone, "+919876540151")

    def test_inbound_never_uses_room_name_token(self):
        direction, phone = piopiy_agent_worker.resolve_call_context(
            {"to_number": "917943446755", "room_name": "piopiyai_0151_xyz"}
        )
        self.assertEqual(direction, "inbound")
        self.assertEqual(phone, "+910000000000")

    def test_outbound_room_token_resolves_only_unique_registered_dossier(self):
        mgr = precall_manager.manager
        mgr.register_precall(phone="+916006760151", name="Aashirwad", prewarm_audio=False)
        ctx = {"from_number": "917943446755", "room_name": "piopiyai_0151_XKPp"}
        direction, phone = piopiy_agent_worker.resolve_call_context(ctx)
        self.assertEqual(direction, "outbound")
        self.assertEqual(phone, "+916006760151")


if __name__ == "__main__":
    unittest.main()
