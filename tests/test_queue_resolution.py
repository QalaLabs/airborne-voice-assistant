import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

import config
import main
import precall_manager
import telephony


class QueueResolutionTests(unittest.TestCase):
    PHONE = "+919818282209"

    def setUp(self):
        self._saved_token = config.AGENT_TOKEN
        self._saved_telecmi_token = config.TELECMI_TOKEN
        self._saved_app_id = config.TELECMI_PIOPIY_APP_ID
        self._saved_api_secret = config.API_SHARED_SECRET
        self._saved_force_pcmo = telephony.FORCE_PCMO_OUTBOUND

        config.AGENT_TOKEN = "test_token"
        config.TELECMI_TOKEN = "test_token"
        config.TELECMI_PIOPIY_APP_ID = "test_agent_123"
        config.API_SHARED_SECRET = "test_secret"
        telephony.FORCE_PCMO_OUTBOUND = False

        telephony.cancel_all_watchers()
        telephony.release_active_call(self.PHONE)
        precall_manager.manager.register_precall(phone=self.PHONE, name="Test Candidate", prewarm_audio=False)

    def tearDown(self):
        config.AGENT_TOKEN = self._saved_token
        config.TELECMI_TOKEN = self._saved_telecmi_token
        config.TELECMI_PIOPIY_APP_ID = self._saved_app_id
        config.API_SHARED_SECRET = self._saved_api_secret
        telephony.FORCE_PCMO_OUTBOUND = self._saved_force_pcmo
        telephony.cancel_all_watchers()
        telephony.release_active_call(self.PHONE)

    def test_outbound_dispatch_arms_verification_watcher(self):
        """Verifies that an AI call dispatch returns QUEUED and starts a verification watcher."""
        mock_client = MagicMock()
        mock_client.ai.call.return_value = {"request": "req-ai-101", "message": "call_queued"}

        voice_mod = SimpleNamespace(RestClient=lambda token: mock_client)
        with patch.dict(sys.modules, {"piopiy.voice": voice_mod}), \
             patch.object(telephony.supabase_client, "save_conversation_history"), \
             patch("assistant.get_greeting_voice_url", return_value="https://x/g.mp3"):

            res = telephony.dispatch_outbound_call(self.PHONE, "Aayush")
            self.assertTrue(res["ok"])
            self.assertEqual(res["provider"], "piopiy_ai")
            self.assertEqual(res["request_id"], "req-ai-101")
            self.assertEqual(res["status"], "QUEUED")
            self.assertTrue(res["verification_active"])

            # Verify status in telephony tracker
            status_data = telephony.get_dispatched_call_status(self.PHONE)
            self.assertEqual(status_data["status"], "QUEUED")
            self.assertEqual(status_data["provider"], "piopiy_ai")

    def test_ringing_event_satisfies_verification_watcher(self):
        """When carrier or worker reports RINGING, the status updates and watcher is satisfied."""
        mock_client = MagicMock()
        mock_client.ai.call.return_value = {"request": "req-ai-102", "message": "call_queued"}

        voice_mod = SimpleNamespace(RestClient=lambda token: mock_client)
        with patch.dict(sys.modules, {"piopiy.voice": voice_mod}), \
             patch.object(telephony.supabase_client, "save_conversation_history"), \
             patch("assistant.get_greeting_voice_url", return_value="https://x/g.mp3"):

            telephony.dispatch_outbound_call(self.PHONE, "Aayush")
            self.assertEqual(telephony.get_dispatched_call_status(self.PHONE)["status"], "QUEUED")

            # Simulate carrier webhook delivering a 'ringing' event
            telephony.mark_call_progress(self.PHONE, "RINGING")
            self.assertEqual(telephony.get_dispatched_call_status(self.PHONE)["status"], "RINGING")

            # Simulate worker connecting session
            telephony.mark_call_progress(self.PHONE, "CONNECTED", call_id="session-456")
            status_data = telephony.get_dispatched_call_status(self.PHONE)
            self.assertEqual(status_data["status"], "CONNECTED")
            self.assertEqual(status_data.get("call_id"), "session-456")

    def test_queue_stall_triggers_automatic_pcmo_recovery(self):
        """When an AI call stalls in queue without ringing, fallback to client.pcmo.call is executed."""
        mock_client = MagicMock()
        mock_client.ai.call.return_value = {"request": "req-ai-stalled", "message": "call_queued"}
        mock_client.pcmo.call.return_value = {"request": "req-pcmo-fallback", "message": "call_queued"}

        voice_mod = SimpleNamespace(RestClient=lambda token: mock_client)
        with patch.dict(sys.modules, {"piopiy.voice": voice_mod}), \
             patch.object(telephony.supabase_client, "save_conversation_history"), \
             patch("assistant.get_greeting_voice_url", return_value="https://x/g.mp3"):

            # Set short verification timeout for test (0.1 seconds)
            with patch.object(telephony, "CALL_VERIFICATION_TIMEOUT_SECS", 0.1):
                res = telephony.dispatch_outbound_call(self.PHONE, "Deepak")
                self.assertTrue(res["ok"])
                self.assertEqual(res["status"], "QUEUED")

                # Allow watcher timer to fire
                time.sleep(0.25)

                # Verify PCMO fallback was dispatched
                mock_client.pcmo.call.assert_called_once()
                parent_status = telephony.get_dispatched_call_status("req-ai-stalled")
                self.assertEqual(parent_status.get("status"), "FALLBACK_PCMO_DISPATCHED")

                fallback_status = telephony.get_dispatched_call_status("req-pcmo-fallback")
                self.assertEqual(fallback_status.get("provider"), "piopiy_pcmo_fallback")

    def test_force_pcmo_outbound_bypasses_ai_queue(self):
        """FORCE_PCMO_OUTBOUND=True bypasses the client.ai.call queue and dials via client.pcmo.call."""
        telephony.FORCE_PCMO_OUTBOUND = True
        mock_client = MagicMock()
        mock_client.pcmo.call.return_value = {"request": "req-pcmo-direct", "message": "call_queued"}

        voice_mod = SimpleNamespace(RestClient=lambda token: mock_client)
        with patch.dict(sys.modules, {"piopiy.voice": voice_mod}), \
             patch.object(telephony.supabase_client, "save_conversation_history"), \
             patch("assistant.get_greeting_voice_url", return_value="https://x/g.mp3"):

            res = telephony.dispatch_outbound_call(self.PHONE, "Direct Lead")
            self.assertTrue(res["ok"])
            self.assertEqual(res["provider"], "piopiy_pcmo")
            self.assertEqual(res["request_id"], "req-pcmo-direct")
            mock_client.ai.call.assert_not_called()
            mock_client.pcmo.call.assert_called_once()

    def test_status_endpoint_reports_live_delivery_state(self):
        """GET /api/calls/status/{phone} returns 200 with delivery state."""
        client = TestClient(main.app)
        headers = {"X-API-Key": "test_secret"}

        telephony.mark_call_progress(self.PHONE, "CONNECTED", call_id="c-999")
        # Ensure tracking entry exists
        telephony._dispatched_calls["req-live"] = {
            "phone": self.PHONE,
            "status": "CONNECTED",
            "call_id": "c-999",
            "provider": "piopiy_ai"
        }
        digits = "".join(filter(str.isdigit, self.PHONE))
        telephony._phone_to_req[digits] = "req-live"

        r = client.get(f"/api/calls/status/{self.PHONE}", headers=headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "found")
        self.assertEqual(data["call"]["status"], "CONNECTED")

    def test_pcmo_connect_pipeline_schema_valid_against_real_piopiy_validator(self):
        """Ensures that the connect action pipeline strictly conforms to Piopiy validators."""
        from piopiy.voice.validators import _validate_connect_action, validate_pcmo_call_request

        caller_id = "917948568600"
        app_id = "edc5b96c-9e10-4b1f-b2b0-528da3c30978"

        pipeline = [
            {
                "action": "connect",
                "params": {
                    "caller_id": caller_id,
                    "options": {
                        "recording": {
                            "enabled": True
                        }
                    }
                },
                "endpoints": [
                    {
                        "type": "agent",
                        "id": app_id
                    }
                ]
            }
        ]

        # 1. Action level validator
        _validate_connect_action(pipeline[0], "pipeline[0]")

        # 2. Top-level PCMO call payload validator
        payload = {
            "caller_id": caller_id,
            "to_number": "919818282209",
            "app_id": app_id,
            "pipeline": pipeline
        }
        validate_pcmo_call_request(payload)


if __name__ == "__main__":
    unittest.main()
