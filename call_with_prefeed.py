"""
CLI tool & verification runner to feed lead intelligence to the AI Voice Assistant
before making an outbound call, ensuring sub-second response times and zero-latency audio.

Usage examples:
  1. Dry-run inspection (see prompt, greeting, and pre-warm status):
     python call_with_prefeed.py --phone +919811817062 --name "Deepak" --course "CPL Ground School" --education "12th Commerce (Non-PCM)" --notes "Asked about NIOS and loan" --dry-run

  2. Make an outbound call with pre-fed dossier:
     python call_with_prefeed.py --phone +919811817062 --name "Deepak" --course "CPL Ground School" --education "12th Arts" --objective "Confirm NIOS, quote 2.7L, invite to Dwarka campus"

  3. Feed info via API endpoint:
     curl -X POST http://localhost:8000/api/calls/prefeed -H "Content-Type: application/json" -d '{"phone": "+919811817062", "name": "Deepak", "education": "12th Arts"}'
"""

import sys
import argparse
import json
import time

import precall_manager
import telephony

def main():
    parser = argparse.ArgumentParser(description="Feed lead data to Airborne Voice Agent before calling.")
    parser.add_argument("--phone", required=True, help="Target phone number with country code (e.g. +919811817062)")
    parser.add_argument("--name", default="Candidate", help="Lead name")
    parser.add_argument("--course", default="Commercial Pilot License (CPL)", help="Inquired course")
    parser.add_argument("--education", default=None, help="Educational background (e.g. '12th Arts Non-PCM', '12th PCM 85%')")
    parser.add_argument("--age", default=None, help="Candidate age (e.g. 18)")
    parser.add_argument("--city", default="Delhi NCR", help="Candidate city / location")
    parser.add_argument("--aviation-exp", default="None", help="Prior flying experience (e.g. 'None', 'Holds CPL', '50 hrs')")
    parser.add_argument("--medicals", default=None, help="Medical / glasses status (e.g. 'Wears glasses', 'Needs Class 2')")
    parser.add_argument("--budget", default=None, help="Budget / loan info (e.g. 'Needs bank loan')")
    parser.add_argument("--notes", default=None, help="Prior WhatsApp or form notes")
    parser.add_argument("--objective", default=None, help="Tactical call objective")
    parser.add_argument("--language", default="Hinglish", choices=["English", "Hindi", "Hinglish"])
    parser.add_argument("--dry-run", action="store_true", help="Only show pre-compiled dossier and prompt without dialing")

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  AIRBORNE AVIATION VOICE AGENT - PRE-CALL FEEDING & WARM-UP")
    print("=" * 70)

    t0 = time.time()
    dossier = precall_manager.manager.register_precall(
        phone=args.phone,
        name=args.name,
        course_interest=args.course,
        education=args.education,
        age=args.age,
        city=args.city,
        prior_aviation_exp=args.aviation_exp,
        medicals_status=args.medicals,
        budget_or_loan=args.budget,
        notes=args.notes,
        call_objective=args.objective,
        preferred_language=args.language,
        source="CLI_PREFEED",
        prewarm_audio=not args.dry_run
    )
    t_reg = (time.time() - t0) * 1000

    greeting = precall_manager.manager.generate_greeting(dossier, direction="outbound")
    compiled_prompt = precall_manager.manager.compile_system_prompt(dossier, direction="outbound")

    print(f"\n[OK] Dossier Registered in {t_reg:.1f}ms")
    print(f" -> Candidate:   {dossier.name} ({dossier.phone})")
    print(f" -> Program:     {dossier.course_interest}")
    print(f" -> Education:   {dossier.education or 'Standard'}")
    print(f" -> City:        {dossier.city}")
    print(f" -> Objective:   {dossier.call_objective or 'Standard qualification'}")
    print(f"\n[Personalized Opening Greeting (0ms Target)]:\n  \"{greeting}\"")
    print(f"\n[Pre-Compiled System Prompt Length]: {len(compiled_prompt)} characters")
    print("-" * 70)
    print(compiled_prompt)
    print("-" * 70)

    if args.dry_run:
        print("\n[Dry Run Completed] No outbound phone call placed.")
        return

    print(f"\n[Initiating Call] Dialing {dossier.phone} with pre-warmed audio and pre-fed context...")
    success = telephony.make_outbound_call(
        phone_number=dossier.phone,
        lead_name=dossier.name,
        precall_data=dossier.to_dict()
    )

    if success:
        print(f"[SUCCESS] Outbound call placed to {dossier.name} ({dossier.phone}).")
    else:
        print(f"[ERROR] Failed to place outbound call.")

if __name__ == "__main__":
    main()
