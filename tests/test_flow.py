import unittest
import json
import assistant
import rag
import supabase_client
import scheduler

class TestAirborneAssistantFlow(unittest.TestCase):
    
    def setUp(self):
        # Clear mock histories
        assistant.histories.clear()
        
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
        
    def test_conversation_loop(self):
        """
        Tests dialogue state management in the recording assistant loop.
        """
        phone = "+919999999999"
        
        # First turn: Intro/Interest
        audio_url, should_hang_up = assistant.handle_conversation("https://mock-twilio-recording/rec1.wav", phone, "inbound")
        self.assertFalse(should_hang_up)
        self.assertIn(phone, assistant.histories)
        
        # Second turn: user ends conversation
        assistant.histories[phone].append({"role": "user", "content": "Thank you, goodbye!"})
        # Simulate LLM outputting exit phrase trigger
        assistant.histories[phone].append({"role": "assistant", "content": "You are welcome. Have a safe flight! [EXIT]"})
        
        # Detects exit
        transcript = assistant.get_transcript_string(phone)
        self.assertIn("[EXIT]", transcript)

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
        # Clean up job
        if scheduler.scheduler:
            scheduler.scheduler.remove_job(job_id)

if __name__ == "__main__":
    unittest.main()
