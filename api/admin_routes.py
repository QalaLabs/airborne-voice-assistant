"""
VAGADK Admin REST Endpoints (Interface 2)
FastAPI routes for developer issue review, verification, and lesson management.
"""

from fastapi import APIRouter, HTTPException, Query, Header, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import database

router = APIRouter(prefix="/api/admin", tags=["Agent Quality & Learning"])

class VerifyRequest(BaseModel):
    priority: int = 7
    notes: Optional[str] = "Approved by developer"

class RejectRequest(BaseModel):
    reason: Optional[str] = "False positive"

class LessonUpdateRequest(BaseModel):
    is_active: bool
    priority_score: int
    rule_instruction: str
    negative_constraint: str

@router.get("/issues")
def get_issues(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = 50
):
    conn = database.get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    with conn.cursor() as cur:
        query = """
            SELECT id, call_id, customer_phone, direction, mistake_category, severity,
                   turn_index, caller_utterance, agent_response, critic_reasoning,
                   suggested_correction, proposed_negative_constraint, status, reviewer_notes, created_at
            FROM agent_issues
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND status = %s"
            params.append(status.upper())
        if severity:
            query += " AND severity = %s"
            params.append(severity.upper())

        query += " ORDER BY id DESC LIMIT %s;"
        params.append(limit)

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "call_id": r[1],
            "customer_phone": r[2],
            "direction": r[3],
            "mistake_category": r[4],
            "severity": r[5],
            "turn_index": r[6],
            "caller_utterance": r[7],
            "agent_response": r[8],
            "critic_reasoning": r[9],
            "suggested_correction": r[10],
            "proposed_negative_constraint": r[11],
            "status": r[12],
            "reviewer_notes": r[13],
            "created_at": r[14].isoformat() if r[14] else None
        }
        for r in rows
    ]

@router.post("/issues/{issue_id}/verify")
def verify_issue(issue_id: int, req: VerifyRequest):
    conn = database.get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE agent_issues
            SET status = 'VERIFIED_BY_DEV', reviewer_notes = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING proposed_negative_constraint, suggested_correction, mistake_category;
        """, (req.notes, issue_id))
        res = cur.fetchone()
        if not res:
            raise HTTPException(status_code=404, detail="Issue not found")

        neg_constraint, correction, category = res

        # Update or create active lesson
        cur.execute("""
            UPDATE agent_lessons
            SET is_active = TRUE, priority_score = %s, verified_by = 'DEV_WEB'
            WHERE source_issue_id = %s;
        """, (req.priority, issue_id))

        if cur.rowcount == 0 and neg_constraint:
            cur.execute("""
                INSERT INTO agent_lessons
                (source_issue_id, topic_tag, rule_instruction, negative_constraint, priority_score, is_active, verified_by)
                VALUES (%s, %s, %s, %s, %s, TRUE, 'DEV_WEB');
            """, (issue_id, category, correction, neg_constraint, req.priority))

        conn.commit()

    return {"status": "SUCCESS", "message": f"Issue #{issue_id} verified and active in live call prompts"}

@router.post("/issues/{issue_id}/reject")
def reject_issue(issue_id: int, req: RejectRequest):
    conn = database.get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE agent_issues
            SET status = 'REJECTED', reviewer_notes = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (req.reason, issue_id))

        cur.execute("""
            UPDATE agent_lessons
            SET is_active = FALSE
            WHERE source_issue_id = %s;
        """, (issue_id,))
        conn.commit()

    return {"status": "SUCCESS", "message": f"Issue #{issue_id} marked as REJECTED"}

@router.get("/lessons")
def get_lessons():
    conn = database.get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, source_issue_id, topic_tag, rule_instruction, negative_constraint, priority_score, is_active, verified_by, created_at
            FROM agent_lessons
            ORDER BY is_active DESC, priority_score DESC, id DESC;
        """)
        rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "source_issue_id": r[1],
            "topic_tag": r[2],
            "rule_instruction": r[3],
            "negative_constraint": r[4],
            "priority_score": r[5],
            "is_active": r[6],
            "verified_by": r[7],
            "created_at": r[8].isoformat() if r[8] else None
        }
        for r in rows
    ]

@router.get("/metrics/summary")
def get_metrics_summary():
    conn = database.get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                COUNT(*) as total_calls,
                ROUND(AVG(caller_sentiment_score)::numeric, 2) as avg_sentiment,
                ROUND(AVG(factual_accuracy_score)::numeric, 2) as avg_accuracy,
                SUM(CASE WHEN friction_detected THEN 1 ELSE 0 END) as friction_count,
                SUM(CASE WHEN compliance_passed THEN 1 ELSE 0 END) as clean_calls
            FROM agent_eval_metrics;
        """)
        r = cur.fetchone()

    return {
        "total_calls": r[0] or 0,
        "avg_sentiment": float(r[1]) if r[1] is not None else 0.0,
        "avg_accuracy": float(r[2]) if r[2] is not None else 1.0,
        "friction_count": r[3] or 0,
        "clean_calls": r[4] or 0
    }
