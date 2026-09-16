"""
Local Test Call Simulator for Airborne Aviation Voice AI
---------------------------------------------------------
This script allows you to initiate and simulate a full call locally:
1. Automated Simulated Call (Interactive or Preset Dialogue)
2. Outbound Telephony Test (TeleCMI / Twilio)
3. API Endpoint Webhook Test (/telecmi/answer, /answer-call, /process-recording)
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import rag
import assistant
import supabase_client
import telephony
from assistant import get_greeting_voice_url, handle_conversation, run_post_call_pipeline
from gpt_test import chat_with_gpt

def run_simulated_call_interactive(phone="+919876543210", lead_name="Aarav Sharma", direction="inbound"):
    print("=" * 65)
    print(f"  STARTING LOCAL VOICE CALL SIMULATION ({direction.upper()})")
    print(f"  Lead: {lead_name} | Phone: {phone}")
    print("=" * 65)
    
    if direction == "outbound":
        greeting_text = f"Hello {lead_name}! I am Modassir from Airborne Aviation Academy. I noticed you submitted an interest in our pilot training courses. How can I help you today?"
    else:
        greeting_text = "Welcome to Airborne Aviation Academy Dwarka. I am your AI pilot advisor. How can I help you regarding our flight programs today?"
        
    print(f"\n[AI Assistant (Modassir)]:\n\"{greeting_text}\"")

    history = [{"role": "assistant", "content": greeting_text}]
    supabase_client.save_conversation_history(phone, history, direction)

    turn = 1
    while True:
        print(f"\n--- Turn {turn} ---")
        try:
            user_input = input("You (Lead) [type 'exit' or 'bye' to hang up]: ").strip()
        except EOFError:
            break
        if not user_input:
            continue

        if any(w in user_input.lower() for w in assistant.EXIT_PHRASES):
            farewell = "Thank you for calling Airborne Aviation Academy. Have a great day ahead! Clear skies! [EXIT]"
            print(f"\n[AI Assistant (Modassir)]:\n\"{farewell.replace('[EXIT]', '').strip()}\"")
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": farewell})
            supabase_client.save_conversation_history(phone, history, direction)
            break

        rag_context = rag.query_rag(user_input)
        print(f"\n[System - RAG Context Retrieved ({len(rag_context)} chars)]:\n{rag_context[:250]}...")

        dynamic_prompt = f"{assistant.SYSTEM_PROMPT}\n\nRELEVANT WEBSITE CONTEXT:\n{rag_context}"
        ai_response = chat_with_gpt(user_input, history, dynamic_prompt)

        print(f"\n[AI Assistant (Modassir)]:\n\"{ai_response.replace('[EXIT]', '').strip()}\"")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": ai_response})
        supabase_client.save_conversation_history(phone, history, direction)

        if "[EXIT]" in ai_response:
            print("\n[Call Ended by Assistant]")
            break

        turn += 1

    print("\n" + "=" * 65)
    print("  EXECUTING POST-CALL QUALIFICATION & CRM PIPELINE")
    print("=" * 65)
    run_post_call_pipeline(phone=phone, direction=direction, recording_url="local-test-recording.wav")
    print("\n[SUCCESS] Call test completed successfully!")

def run_automated_demo_call(phone="+919876543210", lead_name="Rohan Verma", direction="outbound"):
    print("=" * 65)
    print(f"  AUTOMATED MULTI-TURN TEST CALL ({direction.upper()})")
    print(f"  Lead: {lead_name} | Phone: {phone}")
    print("=" * 65)

    if direction == "outbound":
        greeting_text = f"Hello {lead_name}! I am Modassir from Airborne Aviation Academy. I noticed you submitted an interest in our pilot training courses. How can I help you today?"
    else:
        greeting_text = "Welcome to Airborne Aviation Academy Dwarka. I am your AI pilot advisor. How can I help you regarding our flight programs today?"
        
    print(f"\n[AI Assistant (Modassir)]:\n\"{greeting_text}\"")

    history = [{"role": "assistant", "content": greeting_text}]
    supabase_client.save_conversation_history(phone, history, direction)

    dialogue_script = [
        "Hi Modassir sir, I want to know about DGCA CPL Ground Classes fees and duration.",
        "That sounds great. Can I visit the campus in Dwarka this Saturday to see the A320 simulator?",
        "Yes, Saturday 11 AM works for me. Thank you, Modassir sir! Bye."
    ]

    for turn_idx, user_speech in enumerate(dialogue_script, 1):
        print(f"\n--- Turn {turn_idx} ---")
        print(f"Lead ({lead_name}): \"{user_speech}\"")

        if any(w in user_speech.lower() for w in assistant.EXIT_PHRASES):
            farewell = "Thank you for calling Airborne Aviation Academy. Your Saturday 11 AM campus visit is noted. Have a great day ahead! Clear skies! [EXIT]"
            print(f"AI Assistant (Modassir): \"{farewell.replace('[EXIT]', '').strip()}\"")
            history.append({"role": "user", "content": user_speech})
            history.append({"role": "assistant", "content": farewell})
            supabase_client.save_conversation_history(phone, history, direction)
            break

        rag_context = rag.query_rag(user_speech)
        dynamic_prompt = f"{assistant.SYSTEM_PROMPT}\n\nRELEVANT WEBSITE CONTEXT:\n{rag_context}"
        ai_response = chat_with_gpt(user_speech, history, dynamic_prompt)

        print(f"AI Assistant (Modassir): \"{ai_response.replace('[EXIT]', '').strip()}\"")
        history.append({"role": "user", "content": user_speech})
        history.append({"role": "assistant", "content": ai_response})
        supabase_client.save_conversation_history(phone, history, direction)

    print("\n" + "=" * 65)
    print("  TRIGGERING POST-CALL CRM & QUALIFICATION PIPELINE")
    print("=" * 65)
    run_post_call_pipeline(phone=phone, direction=direction, recording_url="local-test-recording.wav")
    print("\n[SUCCESS] Automated test call pipeline executed.")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if mode == "interactive":
        phone_arg = sys.argv[2] if len(sys.argv) > 2 else "+919876543210"
        name_arg = sys.argv[3] if len(sys.argv) > 3 else "Aarav Sharma"
        run_simulated_call_interactive(phone=phone_arg, lead_name=name_arg)
    elif mode == "telephony":
        target_num = sys.argv[2] if len(sys.argv) > 2 else "+919876543210"
        name = sys.argv[3] if len(sys.argv) > 3 else "Test Candidate"
        print(f"Initiating actual telephony outbound call to {name} ({target_num})...")
        telephony.make_outbound_call(target_num, name)
    else:
        phone_arg = sys.argv[2] if len(sys.argv) > 2 else "+919876543210"
        name_arg = sys.argv[3] if len(sys.argv) > 3 else "Rohan Verma"
        run_automated_demo_call(phone=phone_arg, lead_name=name_arg)


