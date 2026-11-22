import unittest
import time
from unittest.mock import MagicMock, patch
import telephony

class ConcurrencyQueueTests(unittest.TestCase):
    def setUp(self):
        telephony.clear_all_active_calls()
        telephony.clear_waiting_queue()
        telephony.cancel_all_watchers()

    def tearDown(self):
        telephony.clear_all_active_calls()
        telephony.clear_waiting_queue()
        telephony.cancel_all_watchers()

    def test_concurrency_limit_is_four(self):
        self.assertEqual(telephony.MAX_CONCURRENT_CALLS, 4)

    def test_active_slots_acquire_up_to_four(self):
        p1 = "+919818000001"
        p2 = "+919818000002"
        p3 = "+919818000003"
        p4 = "+919818000004"
        p5 = "+919818000005"

        self.assertTrue(telephony.register_active_call(p1))
        self.assertTrue(telephony.register_active_call(p2))
        self.assertTrue(telephony.register_active_call(p3))
        self.assertTrue(telephony.register_active_call(p4))
        self.assertEqual(telephony.get_active_calls_count(), 4)

        # 5th attempt must return False (all 4 slots busy)
        self.assertFalse(telephony.register_active_call(p5))

    def test_inbound_and_outbound_shared_concurrency_ceiling(self):
        """Rule 9: Enforce that the 4-call limit strictly pools BOTH inbound and outbound calls."""
        # 2 Inbound calls
        self.assertTrue(telephony.register_active_call("+919818000011", direction="inbound"))
        self.assertTrue(telephony.register_active_call("+919818000012", direction="inbound"))

        # 2 Outbound calls
        self.assertTrue(telephony.register_active_call("+919818000013", direction="outbound"))
        self.assertTrue(telephony.register_active_call("+919818000014", direction="outbound"))

        # Total active is 4
        self.assertEqual(telephony.get_active_calls_count(), 4)
        breakdown = telephony.get_active_calls_breakdown()
        self.assertEqual(breakdown["total"], 4)
        self.assertEqual(breakdown["inbound"], 2)
        self.assertEqual(breakdown["outbound"], 2)
        self.assertEqual(breakdown["available_slots"], 0)

        # 5th Inbound call rejected
        self.assertFalse(telephony.register_active_call("+919818000015", direction="inbound"))

        # 5th Outbound call queued
        res5 = telephony.dispatch_outbound_call("+919818000015", "Lead Five", bypass_cooldown=True)
        self.assertTrue(res5["ok"])
        self.assertEqual(res5["status"], "QUEUED_LINE")

        # Releasing 1 inbound call frees a slot for queued outbound
        telephony.release_active_call("+919818000011")
        time.sleep(1.2)
        self.assertLessEqual(telephony.get_active_calls_count(), 4)

    def test_sixty_second_outbound_cooldown(self):
        """Rule 9: Enforce minimum 60-second cooldown per target phone number to avoid room collisions."""
        phone = "+919818223344"
        telephony.clear_cooldowns()

        # First dispatch should be allowed (or queued if busy, but cooldown is registered)
        res1 = telephony.dispatch_outbound_call(phone, "Candidate Alpha")
        self.assertTrue(res1["ok"])

        # Immediate second dispatch to the same number must be blocked by 60s cooldown
        res2 = telephony.dispatch_outbound_call(phone, "Candidate Alpha")
        self.assertFalse(res2["ok"])
        self.assertEqual(res2["status"], "COOLDOWN_ACTIVE")
        self.assertIn("60-second cooldown active", res2["error"])
        self.assertGreater(res2["cooldown_remaining_secs"], 0)

        # Different phone number is NOT blocked by cooldown
        different_phone = "+919818223355"
        res3 = telephony.dispatch_outbound_call(different_phone, "Candidate Beta")
        self.assertTrue(res3["ok"])

        # Bypassing cooldown explicitly allows dispatch
        res4 = telephony.dispatch_outbound_call(phone, "Candidate Alpha", bypass_cooldown=True)
        self.assertTrue(res4["ok"])

    def test_rule_1_worker_single_instance_lock(self):
        """Rule 1: Enforce single-instance worker lockfile to prevent LiveKit DuplicateIdentity disconnects."""
        import piopiy_agent_worker
        piopiy_agent_worker.release_worker_lock()

        # First acquisition must succeed
        self.assertTrue(piopiy_agent_worker.acquire_worker_lock())

        # Cleanup releases the lock
        piopiy_agent_worker.release_worker_lock()
        self.assertIsNone(piopiy_agent_worker._worker_lock_file_handle)

    def test_line_up_queue_on_concurrency_saturation(self):
        # Fill 4 active slots
        for i in range(1, 5):
            self.assertTrue(telephony.register_active_call(f"+91981800000{i}"))

        # Dispatch 5th and 6th calls - they should be queued in line instead of rejected
        res5 = telephony.dispatch_outbound_call("+919818000005", "Lead Five")
        self.assertTrue(res5["ok"])
        self.assertEqual(res5["status"], "QUEUED_LINE")
        self.assertEqual(res5["queue_position"], 1)

        res6 = telephony.dispatch_outbound_call("+919818000006", "Lead Six")
        self.assertTrue(res6["ok"])
        self.assertEqual(res6["status"], "QUEUED_LINE")
        self.assertEqual(res6["queue_position"], 2)

        # Check queue status
        st = telephony.get_waiting_queue_status()
        self.assertEqual(st["active_calls_count"], 4)
        self.assertEqual(st["queued_count"], 2)
        self.assertEqual(st["queue"][0]["phone"], "+919818000005")
        self.assertEqual(st["queue"][1]["phone"], "+919818000006")

    def test_agent_freed_dispatches_next_in_line(self):
        # Fill 4 active slots
        for i in range(1, 5):
            self.assertTrue(telephony.register_active_call(f"+91981800000{i}"))

        # Enqueue Lead 5
        res5 = telephony.dispatch_outbound_call("+919818000005", "Lead Five")
        self.assertEqual(res5["status"], "QUEUED_LINE")

        # Mock dispatch_outbound_call for when drain runs
        with patch.object(telephony, "dispatch_outbound_call") as mock_dispatch:
            # Releasing an active call should trigger drain and pop Lead 5
            telephony.release_active_call("+919818000001")
            time.sleep(1.2)  # Wait for daemon thread to drain

            self.assertEqual(telephony.get_active_calls_count(), 3)
            self.assertEqual(len(telephony._call_waiting_queue), 0)
            mock_dispatch.assert_called_once()
            args, kwargs = mock_dispatch.call_args
            self.assertEqual(kwargs["phone_number"], "+919818000005")
            self.assertEqual(kwargs["lead_name"], "Lead Five")

if __name__ == "__main__":
    unittest.main()
