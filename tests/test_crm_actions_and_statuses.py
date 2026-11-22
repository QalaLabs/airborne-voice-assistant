import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import json
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database
import supabase_client
import assistant
import crm_sync

class TestCRMStatusesAndActions(unittest.TestCase):

    def setUp(self):
        self.test_phone = "+919876543210"
        database.clear_conversation_history(self.test_phone)

    def test_crm_status_and_lost_reason_definitions(self):
        """Verifies that all standard CRM lifecycle statuses and lost reasons are defined and recognized."""
        canonical_statuses = [
            "NEW", "CONTACTED", "INTERESTED", "FOLLOW_UP", 
            "COUNSELED", "APPLICATION_SUBMITTED", "CONVERTED", "LOST"
        ]
        for st in canonical_statuses:
            self.assertIn(st, database.CRM_LEAD_STATUSES)
            self.assertIn(st, database.VALID_LEAD_STATUSES)

        disqualification_reasons = [
            "NOT_ELIGIBLE", "PRICE_HIGH", "LOCATION_OUT_OF_SCOPE", 
            "JOB_SEEKER", "NOT_INTERESTED", "INVALID_NUMBER", "LANGUAGE_BARRIER"
        ]
        for r in disqualification_reasons:
            self.assertIn(r, database.CRM_LOST_REASONS)

    def test_parse_flexible_datetime(self):
        """Tests natural language and ISO datetime parsing for follow-ups and meetings."""
        base_time = datetime(2026, 11, 23, 10, 0, 0, tzinfo=timezone.utc)
        
        # Relative hours
        dt_in_2h = database.parse_flexible_datetime("in 2 hours", base_dt=base_time)
        self.assertEqual(dt_in_2h, base_time + timedelta(hours=2))

        # Relative days
        dt_after_3d = database.parse_flexible_datetime("after 3 days", base_dt=base_time)
        self.assertEqual(dt_after_3d, base_time + timedelta(days=3))

        # 'Tomorrow 4 PM' (IST 16:00 is UTC 10:30)
        dt_tomorrow = database.parse_flexible_datetime("Tomorrow 4 PM", base_dt=base_time)
        self.assertIsNotNone(dt_tomorrow)
        self.assertEqual(dt_tomorrow.hour, 10)
        self.assertEqual(dt_tomorrow.minute, 30)

        # Standard ISO string
        iso_str = "2026-11-25T14:30:00Z"
        dt_iso = database.parse_flexible_datetime(iso_str)
        self.assertEqual(dt_iso.isoformat(), "2026-11-25T14:30:00+00:00")

    def test_counselor_assignment_function(self):
        """Tests the counselor lookup and assignment functionality."""
        counselors = database.get_available_counselors()
        self.assertTrue(len(counselors) >= 1)
        self.assertIn("name", counselors[0])

        res = database.assign_counselor_to_lead(
            self.test_phone,
            counselor_name="Senior Admissions Counselor",
            reason="Candidate requested 1-on-1 counseling for CPL Ground School"
        )
        self.assertEqual(res["status"], "ASSIGNED")
        self.assertEqual(res["counselor_name"], "Senior Admissions Counselor")
        self.assertIn("counselor_id", res)

    def test_schedule_followup_function(self):
        """Tests the followup scheduling function."""
        res = database.schedule_followup(
            self.test_phone,
            followup_time="Tomorrow 5 PM",
            notes="Follow up on DGCA 10+2 NIOS admission procedure",
            reason="CALLBACK_REQUESTED"
        )
        self.assertEqual(res["status"], "FOLLOW_UP")
        self.assertIn("next_follow_up", res)
        self.assertIn("NIOS", res["notes"])

    def test_schedule_meeting_function(self):
        """Tests the campus visit / meeting scheduling function."""
        res = database.schedule_meeting(
            self.test_phone,
            meeting_time="Tomorrow 3 PM",
            meeting_type="CAMPUS_VISIT",
            notes="Candidate visiting Ramphal Chowk campus for A320 simulator demo"
        )
        self.assertEqual(res["status"], "INTERESTED")
        self.assertEqual(res["meeting_type"], "CAMPUS_VISIT")
        self.assertIn("Ramphal Chowk", res["location"])
        self.assertIn("next_follow_up", res)

    @patch("crm_sync.requests.post")
    def test_telecrm_sync_payload_with_crm_actions(self, mock_post):
        """Tests that TeleCRM synchronization formats status, counselor, followup, and meeting actions."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch("config.TELECRM_API_KEY", "test-key-123"):
            lead_data = {
                "name": "Rohan Sharma",
                "phone": "+919876543210",
                "email": "rohan@gmail.com",
                "course_interest": "DGCA CPL Ground Classes",
                "classification": "Hot",
                "crm_status": "INTERESTED",
                "counselor_name": "Capt. Navrang Singh",
                "counselor_reason": "High intent CPL candidate",
                "followup_time": "2026-11-24T10:30:00Z",
                "followup_notes": "Call to confirm simulator slot",
                "meeting_time": "2026-11-25T11:00:00Z",
                "meeting_notes": "Campus visit at Ramphal Chowk"
            }
            success = crm_sync.sync_lead_with_telecrm(lead_data, transcript="Caller asked for campus visit.")
            self.assertTrue(success)

            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            
            # Check fields
            self.assertEqual(payload["fields"]["Status"], "INTERESTED")
            self.assertEqual(payload["fields"]["Assigned Counselor"], "Capt. Navrang Singh")
            self.assertEqual(payload["fields"]["Followup Date"], "2026-11-24T10:30:00Z")
            self.assertEqual(payload["fields"]["Meeting Date"], "2026-11-25T11:00:00Z")

            # Check action types
            action_types = [a["type"] for a in payload["actions"]]
            self.assertIn("ASSIGNMENT", action_types)
            self.assertIn("TASK", action_types)
            self.assertIn("MEETING", action_types)
            self.assertIn("SYSTEM_NOTE", action_types)

    @patch("assistant.chat_with_gpt")
    @patch("crm_sync.sync_lead_with_telecrm")
    @patch("automation.trigger_post_call_automations")
    def test_post_call_pipeline_campus_visit_response(self, mock_auto, mock_sync, mock_gpt):
        """Tests that a lead agreeing to a campus visit sets status INTERESTED, schedules meeting & assigns counselor."""
        mock_gpt.return_value = json.dumps({
            "name": "Sameer Verma",
            "email": "sameer@gmail.com",
            "course_interest": "DGCA CPL Ground Classes",
            "user_query": "Wanted to meet Captain Navrang and try A320 simulator",
            "is_18_above": True,
            "city_or_location": "Dwarka Sector 10",
            "confirmed_education_institute": True,
            "open_to_ramphal_chowk": True,
            "booking_intent": "Campus Visit at Ramphal Chowk",
            "scheduled_time": "Tomorrow 3 PM",
            "classification": "Hot",
            "callback_requested": False,
            "callback_time": None,
            "notes": "Booked campus visit tomorrow at 3 PM for simulator session",
            "crm_status": "INTERESTED",
            "lost_reason": None,
            "assign_counselor": True,
            "counselor_assignment_reason": "Booked campus visit and simulator session",
            "followup_required": False,
            "followup_time": None,
            "followup_notes": None,
            "meeting_scheduled": True,
            "meeting_time": "Tomorrow 3 PM",
            "meeting_type": "CAMPUS_VISIT",
            "meeting_notes": "A320 flight simulator session and ground classes roadmap"
        })

        test_transcript = "Caller: Can I visit the academy tomorrow at 3 PM to see the simulator? Agent: Absolutely, I have booked your visit for tomorrow 3 PM."
        assistant.analyze_call_transcript_and_qualify(test_transcript, self.test_phone)

        # Check TeleCRM sync was triggered with proper status & counselor
        self.assertTrue(mock_sync.called)
        sync_payload = mock_sync.call_args[0][0]
        self.assertEqual(sync_payload["crm_status"], "INTERESTED")
        self.assertEqual(sync_payload["meeting_time"], "Tomorrow 3 PM")
        self.assertIsNotNone(sync_payload.get("counselor_name"))

        # Check WhatsApp automation triggered with confirmed campus visit slot
        self.assertTrue(mock_auto.called)
        auto_args = mock_auto.call_args
        self.assertEqual(auto_args[1].get("scheduled_time"), "Tomorrow 3 PM")

    @patch("assistant.chat_with_gpt")
    @patch("crm_sync.sync_lead_with_telecrm")
    @patch("automation.trigger_post_call_automations")
    def test_post_call_pipeline_callback_requested_response(self, mock_auto, mock_sync, mock_gpt):
        """Tests that a lead asking for callback sets status FOLLOW_UP and schedules follow-up task."""
        mock_gpt.return_value = json.dumps({
            "name": "Pooja Malhotra",
            "email": None,
            "course_interest": "Cabin Crew / Flight Attendant Training",
            "user_query": "Driving right now, requested callback tomorrow at 4 PM",
            "is_18_above": True,
            "city_or_location": "Janakpuri",
            "confirmed_education_institute": True,
            "open_to_ramphal_chowk": True,
            "booking_intent": "None",
            "scheduled_time": None,
            "classification": "Warm",
            "callback_requested": True,
            "callback_time": "Tomorrow 4 PM",
            "notes": "Candidate was driving; asked to call back tomorrow at 4 PM",
            "crm_status": "FOLLOW_UP",
            "lost_reason": None,
            "assign_counselor": True,
            "counselor_assignment_reason": "Follow up on cabin crew syllabus",
            "followup_required": True,
            "followup_time": "Tomorrow 4 PM",
            "followup_notes": "Discuss height/age criteria and batch timings",
            "meeting_scheduled": False,
            "meeting_time": None,
            "meeting_type": None,
            "meeting_notes": None
        })

        test_transcript = "Caller: Main abhi driving kar rahi hoon, please mujhe kal 4 baje phone kijiye. Agent: Bilkul, I have scheduled your callback for tomorrow 4 PM."
        assistant.analyze_call_transcript_and_qualify(test_transcript, self.test_phone)

        self.assertTrue(mock_sync.called)
        sync_payload = mock_sync.call_args[0][0]
        self.assertEqual(sync_payload["crm_status"], "FOLLOW_UP")
        self.assertEqual(sync_payload["followup_time"], "Tomorrow 4 PM")

    @patch("assistant.chat_with_gpt")
    @patch("crm_sync.sync_lead_with_telecrm")
    def test_post_call_pipeline_disqualified_lost_response(self, mock_sync, mock_gpt):
        """Tests that a disqualified lead sets status LOST with specific lost_reason."""
        mock_gpt.return_value = json.dumps({
            "name": "Amit Kumar",
            "email": None,
            "course_interest": "General Pilot Training Inquiry",
            "user_query": "Wanted direct job guarantee and has no 10+2 PCM or interest in NIOS",
            "is_18_above": False,
            "city_or_location": "Patna",
            "confirmed_education_institute": False,
            "open_to_ramphal_chowk": False,
            "booking_intent": "None",
            "scheduled_time": None,
            "classification": "Cold",
            "callback_requested": False,
            "callback_time": None,
            "notes": "Underage (15 yrs), demanding written 100% airline job guarantee, unwilling for NIOS",
            "crm_status": "LOST",
            "lost_reason": "NOT_ELIGIBLE",
            "assign_counselor": False,
            "counselor_assignment_reason": None,
            "followup_required": False,
            "followup_time": None,
            "followup_notes": None,
            "meeting_scheduled": False,
            "meeting_time": None,
            "meeting_type": None,
            "meeting_notes": None
        })

        test_transcript = "Caller: Mujhe written job guarantee chahiye. Aur meri age 15 saal hai. Agent: In accordance with DGCA guidelines, minimum age for CPL is 17 and academies do not issue job guarantees."
        assistant.analyze_call_transcript_and_qualify(test_transcript, self.test_phone)

        self.assertTrue(mock_sync.called)
        sync_payload = mock_sync.call_args[0][0]
        self.assertEqual(sync_payload["crm_status"], "LOST")
        self.assertEqual(sync_payload["lost_reason"], "NOT_ELIGIBLE")

if __name__ == "__main__":
    unittest.main()
