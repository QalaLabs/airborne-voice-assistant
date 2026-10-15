import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

import config
import main
import precall_manager
import telephony


def _piopiy_client(ai_call=None, pcmo_call=None):
    client = MagicMock()
    client.ai.call = ai_call or MagicMock(return_value={"request": "req-1", "message": "call_queued"})
    client.pcmo.call = pcmo_call or MagicMock(return_value={"request": "req-2", "message": "call_queued"})
    return client


class ResponseErrorTests(unittest.TestCase):
    def test_detects_failure_bodies(self):
        self.assertEqual(telephony._response_error({"status": "error", "msg": "bad", "code": "cmi-422"}), "bad")
        self.assertEqual(telephony._response_error({"error": "kyc_not_verified"}), "kyc_not_verified")
        self.assertIsNotNone(telephony._response_error({"code": 422, "msg": "x"}))

    def test_accepts_success_bodies(self):
        self.assertIsNone(telephony._response_error({"request": "abc", "message": "call_queued"}))
        self.assertIsNone(telephony._response_error({"status": "ok", "code": 200}))
        self.assertIsNone(telephony._response_error(None))


class DispatchOutboundCallTests(unittest.TestCase):
    PHONE = "+919000000009"

    def setUp(self):
        self._saved = (
            config.AGENT_TOKEN, config.TELECMI_TOKEN, config.TELECMI_APP_ID,
            config.TELECMI_APP_SECRET, config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN,
        )
        config.AGENT_TOKEN = "tok"
        config.TELECMI_TOKEN = "tok"
        config.TELECMI_APP_ID = "123"
        config.TELECMI_APP_SECRET = "sec"
        config.TWILIO_ACCOUNT_SID = ""
        config.TWILIO_AUTH_TOKEN = ""
        precall_manager.manager.register_precall(phone=self.PHONE, name="T", prewarm_audio=False)

    def tearDown(self):
        (config.AGENT_TOKEN, config.TELECMI_TOKEN, config.TELECMI_APP_ID,
         config.TELECMI_APP_SECRET, config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN) = self._saved

    def _dispatch(self, client, rest_response=None):
        voice = SimpleNamespace(RestClient=lambda token: client)
        rest = MagicMock()
        if rest_response is not None:
            rest.return_value = rest_response
        with patch.dict(sys.modules, {"piopiy.voice": voice}), \
             patch.object(telephony.requests, "post", rest), \
             patch.object(telephony.supabase_client, "save_conversation_history"), \
             patch("assistant.get_greeting_voice_url", return_value="https://x/y.mp3"):
            return telephony.dispatch_outbound_call(self.PHONE, "T")

    def test_success_reports_provider_and_request_id(self):
        result = self._dispatch(_piopiy_client())
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "piopiy_ai")
        self.assertEqual(result["request_id"], "req-1")

    def test_kyc_rejection_everywhere_is_reported_as_failure(self):
        kyc = MagicMock(side_effect=Exception("kyc_not_verified"))
        rest = MagicMock(status_code=200, text="{}")
        rest.json.return_value = {"status": "error", "msg": "Invalid type: string (expected number)", "code": "cmi-422"}
        result = self._dispatch(_piopiy_client(ai_call=kyc, pcmo_call=kyc), rest_response=rest)
        self.assertFalse(result["ok"])
        self.assertIn("kyc_not_verified", result["error"])

    def test_http_200_with_error_body_is_not_success(self):
        boom = MagicMock(side_effect=Exception("kyc_not_verified"))
        rest = MagicMock(status_code=200, text="{}")
        rest.json.return_value = {"status": "error", "msg": "nope", "code": "cmi-422"}
        result = self._dispatch(_piopiy_client(ai_call=boom, pcmo_call=boom), rest_response=rest)
        self.assertFalse(result["ok"])

    def test_rest_fallback_success_still_works(self):
        boom = MagicMock(side_effect=Exception("piopiy down"))
        rest = MagicMock(status_code=200, text="{}")
        rest.json.return_value = {"status": "ok", "request_id": "r9"}
        result = self._dispatch(_piopiy_client(ai_call=boom, pcmo_call=boom), rest_response=rest)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "telecmi_rest")

    def test_simulation_only_when_no_carrier_configured(self):
        config.AGENT_TOKEN = config.TELECMI_TOKEN = ""
        config.TELECMI_APP_ID = config.TELECMI_APP_SECRET = ""
        with patch.object(telephony.supabase_client, "save_conversation_history"):
            result = telephony.dispatch_outbound_call(self.PHONE, "T")
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "simulation")


class DispatchEndpointTests(unittest.TestCase):
    def setUp(self):
        self._orig = config.API_SHARED_SECRET
        config.API_SHARED_SECRET = "s3cret"
        self.client = TestClient(main.app)
        self.headers = {"X-API-Key": "s3cret"}
        self.body = {"phone": "+919000000008", "name": "T"}

    def tearDown(self):
        config.API_SHARED_SECRET = self._orig

    def test_carrier_rejection_returns_502_with_error(self):
        failed = {"ok": False, "provider": None, "error": "kyc_not_verified", "request_id": None}
        with patch.object(telephony, "dispatch_outbound_call", return_value=failed):
            r = self.client.post("/api/calls/dispatch", json=self.body, headers=self.headers)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["status"], "error")
        self.assertEqual(r.json()["error"], "kyc_not_verified")

    def test_accepted_call_returns_success_with_request_id(self):
        ok = {"ok": True, "provider": "piopiy_ai", "error": None, "request_id": "req-7"}
        with patch.object(telephony, "dispatch_outbound_call", return_value=ok):
            r = self.client.post("/api/calls/dispatch", json=self.body, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "success")
        self.assertEqual(r.json()["request_id"], "req-7")


if __name__ == "__main__":
    unittest.main()
