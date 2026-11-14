"""
VAGADK Developer CLI Management Tool (Interface 3)
Allows developers to triage, inspect, verify, and reject agent mistakes and manage live negative constraints.
Usage:
    python -m cli.manage_issues --list
    python -m cli.manage_issues --inspect 1
    python -m cli.manage_issues --verify 1 --priority 8
    python -m cli.manage_issues --reject 1 --reason "False alarm"
    python -m cli.manage_issues --lessons
"""

import sys
import os
import argparse

VAGADK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if VAGADK_ROOT not in sys.path:
    sys.path.insert(0, VAGADK_ROOT)

import database

def list_issues(status: str = "PENDING_REVIEW"):
    conn = database.get_connection()
    if not conn:
        print("[ERROR] Cannot connect to database.")
        return

    with conn.cursor() as cur:
        if status.upper() == "ALL":
            cur.execute("""
                SELECT id, call_id, customer_phone, mistake_category, severity, status, created_at
                FROM agent_issues
                ORDER BY id DESC LIMIT 50;
            """)
        else:
            cur.execute("""
                SELECT id, call_id, customer_phone, mistake_category, severity, status, created_at
                FROM agent_issues
                WHERE status = %s
                ORDER BY id DESC LIMIT 50;
            """, (status.upper(),))
        rows = cur.fetchall()

    if not rows:
        print(f"No issues found matching status: {status}")
        return

    print("\n" + "=" * 95)
    print(f"| {'ID':<4} | {'SEVERITY':<8} | {'CATEGORY':<18} | {'PHONE':<15} | {'STATUS':<15} | {'DATE':<18} |")
    print("=" * 95)
    for r in rows:
        created_str = r[6].strftime("%Y-%m-%d %H:%M") if r[6] else "N/A"
        print(f"| {r[0]:<4} | {r[4]:<8} | {r[3]:<18} | {str(r[2]):<15} | {r[5]:<15} | {created_str:<18} |")
    print("=" * 95 + "\n")

def inspect_issue(issue_id: int):
    conn = database.get_connection()
    if not conn:
        print("[ERROR] Cannot connect to database.")
        return

    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, call_id, customer_phone, mistake_category, severity, turn_index,
                   caller_utterance, agent_response, critic_reasoning, suggested_correction,
                   proposed_negative_constraint, status, reviewer_notes, created_at
            FROM agent_issues
            WHERE id = %s;
        """, (issue_id,))
        r = cur.fetchone()

    if not r:
        print(f"[ERROR] Issue #{issue_id} not found.")
        return

    print("\n" + "=" * 80)
    print(f"AGENT ISSUE #{r[0]} DETAILS [{r[4]} - {r[3]}] (Status: {r[11]})")
    print("=" * 80)
    print(f"Call ID:        {r[1]} | Phone: {r[2]} | Date: {r[13]}")
    print(f"Turn Index:     {r[5]}")
    print("\n[CALLER UTTERANCE]:")
    print(f"  \"{r[6]}\"")
    print("\n[AGENT RESPONSE]:")
    print(f"  \"{r[7]}\"")
    print("\n[CRITIC REASONING]:")
    print(f"  {r[8]}")
    print("\n[SUGGESTED CORRECTION]:")
    print(f"  {r[9]}")
    print("\n[PROPOSED NEGATIVE CONSTRAINT (TO INJECT IN PROMPT)]:")
    print(f"  >> {r[10]}")
    if r[12]:
        print(f"\nReviewer Notes: {r[12]}")
    print("=" * 80 + "\n")

def verify_issue(issue_id: int, priority: int = 7, notes: str = "Verified by developer"):
    conn = database.get_connection()
    if not conn:
        print("[ERROR] Cannot connect to database.")
        return

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE agent_issues
            SET status = 'VERIFIED_BY_DEV', reviewer_notes = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING proposed_negative_constraint, suggested_correction, mistake_category;
        """, (notes, issue_id))
        res = cur.fetchone()
        if not res:
            print(f"[ERROR] Issue #{issue_id} not found.")
            return

        neg_constraint, correction, category = res

        # Activate or insert into agent_lessons
        cur.execute("""
            UPDATE agent_lessons
            SET is_active = TRUE, priority_score = %s, verified_by = 'DEV_MANUAL'
            WHERE source_issue_id = %s;
        """, (priority, issue_id))

        if cur.rowcount == 0 and neg_constraint:
            cur.execute("""
                INSERT INTO agent_lessons
                (source_issue_id, topic_tag, rule_instruction, negative_constraint, priority_score, is_active, verified_by)
                VALUES (%s, %s, %s, %s, %s, TRUE, 'DEV_MANUAL');
            """, (issue_id, category, correction, neg_constraint, priority))

        conn.commit()

    print(f"\n[SUCCESS] Issue #{issue_id} verified and activated in live agent prompt with Priority={priority}!\n")

def reject_issue(issue_id: int, reason: str = "Rejected false positive"):
    conn = database.get_connection()
    if not conn:
        print("[ERROR] Cannot connect to database.")
        return

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE agent_issues
            SET status = 'REJECTED', reviewer_notes = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (reason, issue_id))

        cur.execute("""
            UPDATE agent_lessons
            SET is_active = FALSE
            WHERE source_issue_id = %s;
        """, (issue_id,))
        conn.commit()

    print(f"\n[INFO] Issue #{issue_id} marked as REJECTED. Lessons deactivated.\n")

def list_active_lessons():
    conn = database.get_connection()
    if not conn:
        print("[ERROR] Cannot connect to database.")
        return

    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, topic_tag, priority_score, negative_constraint, rule_instruction, verified_by
            FROM agent_lessons
            WHERE is_active = TRUE
            ORDER BY priority_score DESC, id DESC;
        """)
        rows = cur.fetchall()

    if not rows:
        print("\nNo active lessons in database. Using system default cache.")
        return

    print("\n" + "=" * 90)
    print("LIVE AGENT NEGATIVE CONSTRAINTS (CURRENTLY INJECTED IN CALL PROMPTS)")
    print("=" * 90)
    for r in rows:
        print(f"[ID: {r[0]}] [Topic: {r[1]}] [Priority: {r[2]}] (Verified by: {r[5]})")
        print(f"  Constraint:  {r[3]}")
        print(f"  Correction:  {r[4]}")
        print("-" * 90)
    print("=" * 90 + "\n")

def main():
    parser = argparse.ArgumentParser(description="VAGADK Agent Issue & Learning Management CLI")
    parser.add_argument("--list", action="store_true", help="List recorded agent issues")
    parser.add_argument("--status", type=str, default="PENDING_REVIEW", help="Filter status for --list")
    parser.add_argument("--inspect", type=int, help="Inspect full issue details by ID")
    parser.add_argument("--verify", type=int, help="Verify and activate issue constraint in live prompt")
    parser.add_argument("--priority", type=int, default=7, help="Priority score for verified lesson (1-10)")
    parser.add_argument("--reject", type=int, help="Reject issue as false positive")
    parser.add_argument("--reason", type=str, default="Developer reviewed", help="Notes or rejection reason")
    parser.add_argument("--lessons", action="store_true", help="List all currently active prompt constraints")

    args = parser.parse_args()

    if args.list:
        list_issues(status=args.status)
    elif args.inspect:
        inspect_issue(args.inspect)
    elif args.verify:
        verify_issue(args.verify, priority=args.priority, notes=args.reason)
    elif args.reject:
        reject_issue(args.reject, reason=args.reason)
    elif args.lessons:
        list_active_lessons()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
