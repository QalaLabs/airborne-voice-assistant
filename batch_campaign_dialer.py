"""
Batch Campaign Dialer with Pre-Call Context Feeding & Audio Pre-Warming.

Connects directly to Airborne Aviation lead lists (e.g. in Interakt_Imports):
  - CPL_New_Leads.csv
  - CPL_Holder_Leads.csv
  - CabinCrew_Full_New_Leads.csv
  - Simulator_Training_Leads.csv

For every lead:
  1. Maps demographic & form fields into a PreCallDossier.
  2. Injects tailored prompt & tactical objective (zero mid-call RAG latency).
  3. Pre-warms opening greeting audio before placing the call (0ms pickup latency).
  4. Staggers calls with configurable pacing (e.g., 1 call every 2 minutes).

Usage:
  # Dry-run inspection of 3 CPL holder leads:
  python batch_campaign_dialer.py --csv "E:/Airborne Aviation/Interakt_Imports/CPL_Holder_Leads.csv" --limit 3 --dry-run

  # Pre-warm audio and dossiers for 5 new CPL leads into cache:
  python batch_campaign_dialer.py --csv "E:/Airborne Aviation/Interakt_Imports/CPL_New_Leads.csv" --limit 5 --prewarm-only

  # Dial batch of 3 leads with 120-second stagger:
  python batch_campaign_dialer.py --csv "E:/Airborne Aviation/Interakt_Imports/CPL_Holder_Leads.csv" --limit 3 --dial --stagger 120
"""

import os
import sys
import csv
import time
import argparse
from typing import List, Dict, Any

import precall_manager
import telephony

def normalize_phone(phone_str: str) -> str:
    digits = "".join(filter(str.isdigit, str(phone_str or "")))
    if len(digits) == 10:
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    if digits:
        return "+" + digits
    return ""

def map_row_to_dossier_data(row: Dict[str, str], csv_filename: str) -> Dict[str, Any]:
    """
    Intelligently maps different CSV header formats into a clean PreCallDossier payload.
    """
    clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k and v}

    name = row.get("Name") or clean_row.get("name") or "Candidate"
    raw_phone = row.get("Full Phone Number") or row.get("Phone Number") or clean_row.get("full phone number") or clean_row.get("phone number") or clean_row.get("phone") or ""
    phone = normalize_phone(raw_phone)
    city = row.get("city") or clean_row.get("city") or ""
    source = row.get("Campaign Name") or clean_row.get("campaign name") or row.get("Platform") or os.path.basename(csv_filename)

    fname_lower = os.path.basename(csv_filename).lower()

    # Determine course and prior aviation experience
    course_interest = "Commercial Pilot License (CPL)"
    prior_exp = "None"
    education = None
    call_objective = None

    if "cpl_holder" in fname_lower or clean_row.get("are_you_a_cpl_holder?") == "yes":
        course_interest = "Airbus A320 Type Rating & Airline Preparation"
        prior_exp = "Holds Commercial Pilot License (CPL)"
        call_objective = (
            "Candidate ALREADY holds a CPL! Do NOT discuss CPL ground school. "
            "Discuss A320 Type Rating & airline preparation, assess flying hours, "
            "and invite for an A320 simulator walkthrough at Dwarka campus."
        )
    elif "cabin" in fname_lower:
        course_interest = "Cabin Crew Training"
        call_objective = (
            "Qualify for Cabin Crew program (10+2 eligibility, age 18-27, height 155cm+ for females/170cm+ for males). "
            "Invite for personal grooming & interview counseling at Dwarka campus."
        )
    elif "simulator" in fname_lower:
        course_interest = "Airbus A320 Simulator Training"
        call_objective = (
            "Assess candidate's interest in cockpit flight simulator trial. "
            "Book a 1-hour session on the Airbus A320 Fixed-Base Simulator at Dwarka campus."
        )
    else:
        # Standard CPL New / General leads
        grade = clean_row.get("which_grade_is_your_child_in?") or ""
        in_school = clean_row.get("is_your_child_currently_in_school_or_college?") or ""
        if grade or in_school:
            education = f"{grade.replace('_', ' ')} ({in_school.replace('_', ' ')})".strip()
        call_objective = (
            "Qualify 10+2 PCM status (or explain NIOS open school acceptance if Non-PCM), "
            "quote Rs. 2.7 Lakhs ground school tuition, and invite to Dwarka campus for counseling."
        )

    return {
        "phone": phone,
        "name": name,
        "course_interest": course_interest,
        "education": education,
        "city": city,
        "prior_aviation_exp": prior_exp,
        "call_objective": call_objective,
        "source": source
    }

def process_batch(
    csv_path: str,
    limit: int = 10,
    dry_run: bool = True,
    prewarm_only: bool = False,
    dial: bool = False,
    stagger_seconds: int = 120
):
    if not os.path.exists(csv_path):
        print(f"[ERROR] CSV file not found: {csv_path}")
        return

    print("=" * 75)
    print(f"AIRBORNE AVIATION BATCH CAMPAIGN DIALER")
    print(f"Source File: {os.path.basename(csv_path)}")
    print(f"Mode: {'DRY RUN' if dry_run else 'PREWARM ONLY' if prewarm_only else 'LIVE DIALING'}")
    print(f"Limit: {limit} leads | Stagger: {stagger_seconds}s")
    print("=" * 75)

    leads_processed = 0
    with open(csv_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if leads_processed >= limit:
                break

            data = map_row_to_dossier_data(row, csv_path)
            phone = data["phone"]
            if not phone or len(phone) < 10 or "00000000" in phone:
                continue

            leads_processed += 1
            print(f"\n--- Lead #{leads_processed}: {data['name']} ({phone}) ---")
            print(f"Course:    {data['course_interest']}")
            print(f"City:      {data['city'] or 'N/A'}")
            print(f"Exp/Edu:   {data['prior_aviation_exp']} | {data['education'] or 'N/A'}")
            print(f"Objective: {data['call_objective']}")

            # Register dossier
            dossier = precall_manager.manager.register_precall(
                phone=phone,
                name=data["name"],
                course_interest=data["course_interest"],
                education=data["education"],
                city=data["city"],
                prior_aviation_exp=data["prior_aviation_exp"],
                call_objective=data["call_objective"],
                source=data["source"],
                prewarm_audio=not dry_run
            )

            greeting = precall_manager.manager.generate_greeting(dossier, direction="outbound")
            print(f"Opening Greeting: \"{greeting}\"")

            if dry_run:
                continue

            if prewarm_only:
                print(f"[OK] Dossier cached & audio pre-warmed for {data['name']}.")
                continue

            if dial:
                print(f"[CALLING] Initiating outbound call to {data['name']} ({phone})...")
                telephony.make_outbound_call(
                    phone_number=phone,
                    lead_name=data["name"],
                    precall_data=dossier.to_dict()
                )
                if leads_processed < limit:
                    print(f"[WAIT] Staggering next call by {stagger_seconds} seconds to prevent trunk collision...")
                    time.sleep(stagger_seconds)

    print("\n" + "=" * 75)
    print(f"Batch processing completed. Total leads processed: {leads_processed}")
    print("=" * 75)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch campaign dialer with pre-call feeding.")
    parser.add_argument("--csv", required=True, help="Path to lead CSV file")
    parser.add_argument("--limit", type=int, default=5, help="Number of leads to process")
    parser.add_argument("--dry-run", action="store_true", help="Inspect dossiers without pre-warming or calling")
    parser.add_argument("--prewarm-only", action="store_true", help="Pre-warm dossiers and greetings into cache without dialing")
    parser.add_argument("--dial", action="store_true", help="Execute live outbound calls")
    parser.add_argument("--stagger", type=int, default=120, help="Seconds to wait between calls (default: 120)")

    args = parser.parse_args()

    # Determine mode
    is_dial = args.dial
    is_prewarm = args.prewarm_only
    is_dry = args.dry_run or (not is_dial and not is_prewarm)

    process_batch(
        csv_path=args.csv,
        limit=args.limit,
        dry_run=is_dry,
        prewarm_only=is_prewarm,
        dial=is_dial,
        stagger_seconds=args.stagger
    )
