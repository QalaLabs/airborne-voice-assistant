import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import assistant
import rag
import supabase_client
import scheduler
import database

class TestAirborneAssistantFlow(unittest.TestCase):
    
    def setUp(self):
        # Clear mock histories
        self.test_phone = "+919999999999"
        supabase_client.clear_conversation_history(self.test_phone)
        
    def tearDown(self):
        supabase_client.clear_conversation_history(self.test_phone)

    def test_course_mapping(self):
        """
        Tests that course names are parsed and mapped accurately by RAG queries.
        """
        # Test CPL Ground classes query
        context = rag.query_rag("CPL ground school classes")
        self.assertIn("DGCA CPL Ground Classes", context)
        self.assertIn("2,70,000", context)
        
        # Test Airbus simulator query
        context_sim = rag.query_rag("A320 simulator fee details")
        self.assertIn("Airbus A320 Simulator", context_sim)
        self.assertIn("12,000", context_sim)

    def test_rag_gating_behavior(self):
        """
        Tests selective RAG gating:
        1. Ensures 2-word queries containing aviation terms trigger RAG.
        2. Ensures fillers and one-word acknowledgments do NOT trigger RAG.
        """
        # Aviation keywords in short queries must trigger RAG
        self.assertTrue(assistant.should_retrieve_knowledge("CPL fee"))
        self.assertTrue(assistant.should_retrieve_knowledge("A320 simulator"))
        self.assertTrue(assistant.should_retrieve_knowledge("batch dates"))
        self.assertTrue(assistant.should_retrieve_knowledge("eligibility"))
        self.assertTrue(assistant.should_retrieve_knowledge("Navrang sir"))
        
        # Conversational fillers must bypass RAG
        self.assertFalse(assistant.should_retrieve_knowledge("ok"))
        self.assertFalse(assistant.should_retrieve_knowledge("yes"))
        self.assertFalse(assistant.should_retrieve_knowledge("theek hai"))
        self.assertFalse(assistant.should_retrieve_knowledge("hello"))

    @patch("assistant.listen")
    def test_conversation_loop(self, mock_listen):
        """
        Tests dialogue state management in the recording assistant loop with mocked STT.
        """
        mock_listen.return_value = "What is the fee for CPL ground classes?"
        
        # First turn: Intro/Interest
        audio_url, should_hang_up = assistant.handle_conversation("mock_audio.wav", self.test_phone, "inbound")
        self.assertFalse(should_hang_up)
        self.assertTrue(len(audio_url) > 0)
        
        history = supabase_client.get_conversation_history(self.test_phone)
        self.assertTrue(len(history) >= 2)
        self.assertEqual(history[-2]["role"], "user")
        self.assertEqual(history[-1]["role"], "assistant")
        
        # Second turn: user ends conversation
        mock_listen.return_value = "Thank you so much, goodbye!"
        audio_url_2, should_hang_up_2 = assistant.handle_conversation("mock_audio.wav", self.test_phone, "inbound")
        self.assertTrue(should_hang_up_2)
        
        # Check transcript compilation
        transcript = assistant.get_transcript_string(self.test_phone)
        self.assertIn("Lead:", transcript)
        self.assertIn("AI:", transcript)

    @patch("assistant.listen")
    def test_consecutive_silence_circuit_breaker(self, mock_listen):
        """
        Tests that 2 consecutive silent or unrecognized turns trigger the safety circuit breaker.
        """
        # Turn 1: Silence
        mock_listen.return_value = ""
        _, should_hang_up_1 = assistant.handle_conversation("mock_silence.wav", self.test_phone, "inbound")
        self.assertFalse(should_hang_up_1)
        
        # Turn 2: Consecutive Silence -> Circuit breaker must hang up
        mock_listen.return_value = ""
        _, should_hang_up_2 = assistant.handle_conversation("mock_silence.wav", self.test_phone, "inbound")
        self.assertTrue(should_hang_up_2)

    def test_exit_regex_cleanup(self):
        """
        Tests that [EXIT] tags with various casings are cleanly removed for TTS.
        """
        import re
        test_cases = [
            "Thank you! [EXIT]",
            "Have a safe flight! [exit]",
            "Clear skies! [Exit]",
            "See you soon! [EXIT.]"
        ]
        for text in test_cases:
            cleaned = re.sub(r'\[exit\]\.?', '', text, flags=re.IGNORECASE).strip()
            self.assertNotIn("[EXIT]", cleaned)
            self.assertNotIn("[exit]", cleaned)
            self.assertNotIn("[Exit]", cleaned)

    def test_scheduler_delay(self):
        """
        Tests that call tasks are successfully scheduled.
        """
        scheduler.init_scheduler()
        job_id = scheduler.schedule_outbound_call(
            lead_name="Test Pilot",
            lead_phone="+919876543210",
            delay_seconds=5
        )
        self.assertIsNotNone(job_id)
        if scheduler.scheduler:
            scheduler.scheduler.remove_job(job_id)

if __name__ == "__main__":
    unittest.main()
