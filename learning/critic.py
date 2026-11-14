"""
VAGADK Multi-Signal Critic Engine
Analyzes completed call transcripts using three parallel signals:
1. Friction & pushback detection (caller reactions)
2. Ground-truth fact audit (academy policy & DGCA rules)
3. LLM transcript critique (sentiment, concise turn rules, objection handling)
Persists findings into agent_issues and synthesizes actionable negative constraints for agent_lessons.
"""

import sys
import os
import json
import logging
from typing import List, Dict, Any

VAGADK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if VAGADK_ROOT not in sys.path:
    sys.path.insert(0, VAGADK_ROOT)

import database
import gpt_test
from learning.friction_detector import analyze_transcript_friction
from learning.fact_checker import audit_transcript_facts

logger = logging.getLogger("vagadk.critic")

CRITIC_PROMPT_TEMPLATE = """You are the Senior Lead Auditor and Admission Quality Director for Airborne Aviation Academy.
Analyze the following phone call transcript between an Admissions AI Counselor (Piyush) and a prospective student.

EVALUATION CRITERIA:
1. Tone & Brevity: Did the AI keep responses to 2-3 short, natural phone sentences?
2. Language Mirroring: Did the AI match the caller's language (fluent English for English, warm Hinglish for Hindi/Hinglish)?
3. Factual Accuracy: Did the AI make any false promises, incorrect fee quotes, or wrong DGCA eligibility claims?
4. Objection Handling: Did the AI address the caller's concerns or ignore/misunderstand them?

CALL TRANSCRIPT:
{transcript}

OUTPUT FORMAT (Respond STRICTLY with valid JSON only, no markdown, no fences):
{{
    "caller_sentiment_score": 0.8,
    "factual_accuracy_score": 1.0,
    "mistake_detected": false,
    "mistake_category": "NONE",
    "turn_index": 0,
    "caller_utterance": "",
    "agent_response": "",
    "critic_reasoning": "",
    "suggested_correction": "",
    "proposed_negative_constraint": "",
    "severity": "LOW"
}}
"""

def format_transcript_text(call_history: List[Dict[str, str]]) -> str:
    lines = []
    for idx, turn in enumerate(call_history):
        role = "Lead" if turn.get("role") in ["user", "caller"] else "AI Counselor"
        lines.append(f"[Turn {idx}] {role}: {turn.get('content', '')}")
    return "\n".join(lines)

def run_multi_signal_audit(
    customer_phone: str,
    call_history: List[Dict[str, str]],
    direction: str = "INBOUND",
    call_id: str = "unknown"
) -> Dict[str, Any]:
    """
    Executes the full 3-signal post-call audit.
    """
    if not call_history or len(call_history) < 2:
        return {"status": "SKIPPED_INSUFFICIENT_TURNS"}

    # Signal 1: Friction & Pushback Detection
    friction_res = analyze_transcript_friction(call_history)

    # Signal 2: Ground-Truth Fact Audit
    fact_res = audit_transcript_facts(call_history)

    # Signal 3: LLM Judge & Tone Audit
    transcript_text = format_transcript_text(call_history)
    llm_prompt = CRITIC_PROMPT_TEMPLATE.format(transcript=transcript_text)
    
    llm_eval = {}
    try:
        raw_json = gpt_test.chat_with_gemini(
            prompt=llm_prompt,
            system_prompt="You are a strict JSON-only quality assurance auditor.",
            json_mode=True
        )
        # Parse JSON defensively
        cleaned_json = raw_json.strip()
        if cleaned_json.startswith("```"):
            cleaned_json = cleaned_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        llm_eval = json.loads(cleaned_json)
    except Exception as e:
        logger.warning(f"Critic LLM evaluation parse error: {e}")
        llm_eval = {
            "caller_sentiment_score": 0.0,
            "factual_accuracy_score": 1.0,
            "mistake_detected": False
        }

    # Synthesize verdict across all 3 signals
    mistake_detected = False
    category = "NONE"
    severity = "LOW"
    caller_utt = ""
    agent_resp = ""
    reasoning = ""
    correction = ""
    negative_constraint = ""
    turn_idx = 0

    if fact_res.get("factual_error_detected"):
        mistake_detected = True
        category = "FACTUAL_ERROR"
        severity = "CRITICAL"
        turn_idx = fact_res.get("turn_index", 0)
        agent_resp = fact_res.get("agent_response", "")
        caller_utt = call_history[turn_idx - 1].get("content", "") if turn_idx > 0 else ""
        reasoning = fact_res.get("critic_reasoning", "")
        correction = fact_res.get("suggested_correction", "")
        negative_constraint = fact_res.get("negative_constraint", "")

    elif friction_res.get("friction_detected"):
        mistake_detected = True
        category = "USER_CORRECTION"
        severity = friction_res.get("severity", "HIGH")
        turn_idx = friction_res.get("turn_index", 0)
        caller_utt = friction_res.get("caller_utterance", "")
        agent_resp = friction_res.get("agent_prior_response", "")
        reasoning = f"Caller expressed friction ({friction_res.get('friction_type')}): '{caller_utt}'."
        correction = llm_eval.get("suggested_correction") or "Listen carefully and clarify the exact question."
        negative_constraint = llm_eval.get("proposed_negative_constraint") or f"Do NOT repeat prior statements when caller says: '{caller_utt}'"

    elif llm_eval.get("mistake_detected"):
        mistake_detected = True
        category = llm_eval.get("mistake_category", "QUALITY_ISSUE")
        severity = llm_eval.get("severity", "MEDIUM")
        turn_idx = llm_eval.get("turn_index", 0)
        caller_utt = llm_eval.get("caller_utterance", "")
        agent_resp = llm_eval.get("agent_response", "")
        reasoning = llm_eval.get("critic_reasoning", "")
        correction = llm_eval.get("suggested_correction", "")
        negative_constraint = llm_eval.get("proposed_negative_constraint", "")

    # Persist metrics
    sentiment = float(llm_eval.get("caller_sentiment_score", 0.0))
    accuracy = 0.0 if fact_res.get("factual_error_detected") else float(llm_eval.get("factual_accuracy_score", 1.0))
    
    persist_eval_results(
        call_id=call_id,
        phone=customer_phone,
        direction=direction,
        sentiment=sentiment,
        friction_detected=friction_res.get("friction_detected", False),
        friction_type=friction_res.get("friction_type", "NONE"),
        accuracy=accuracy,
        compliance_passed=not mistake_detected,
        total_turns=len(call_history)
    )

    # Persist issue and auto-generate lesson if mistake found
    if mistake_detected:
        issue_id = persist_agent_issue(
            call_id=call_id,
            phone=customer_phone,
            direction=direction,
            category=category,
            severity=severity,
            turn_index=turn_idx,
            caller_utterance=caller_utt,
            agent_response=agent_resp,
            reasoning=reasoning,
            correction=correction,
            negative_constraint=negative_constraint,
            status="PENDING_REVIEW"
        )
        logger.info(f"Recorded Agent Issue #{issue_id} [{category}]: {reasoning}")
        return {
            "status": "ISSUE_RECORDED",
            "issue_id": issue_id,
            "category": category,
            "negative_constraint": negative_constraint
        }

    return {"status": "PASSED_CLEAN"}

def persist_eval_results(call_id, phone, direction, sentiment, friction_detected, friction_type, accuracy, compliance_passed, total_turns):
    try:
        conn = database.get_connection()
        if not conn:
            return
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agent_eval_metrics 
                (call_id, customer_phone, direction, caller_sentiment_score, friction_detected, friction_type, factual_accuracy_score, compliance_passed, total_turns)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (call_id) DO UPDATE SET
                    caller_sentiment_score = EXCLUDED.caller_sentiment_score,
                    friction_detected = EXCLUDED.friction_detected,
                    factual_accuracy_score = EXCLUDED.factual_accuracy_score,
                    compliance_passed = EXCLUDED.compliance_passed;
            """, (call_id, phone, direction, sentiment, friction_detected, friction_type, accuracy, compliance_passed, total_turns))
            conn.commit()
    except Exception as e:
        logger.warning(f"Could not persist agent_eval_metrics: {e}")

def persist_agent_issue(call_id, phone, direction, category, severity, turn_index, caller_utterance, agent_response, reasoning, correction, negative_constraint, status):
    issue_id = None
    try:
        conn = database.get_connection()
        if not conn:
            return None
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agent_issues
                (call_id, customer_phone, direction, mistake_category, severity, turn_index, caller_utterance, agent_response, critic_reasoning, suggested_correction, proposed_negative_constraint, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (call_id, phone, direction, category, severity, turn_index, caller_utterance, agent_response, reasoning, correction, negative_constraint, status))
            issue_id = cur.fetchone()[0]

            # If critical or auto-applied, also stage into agent_lessons in PENDING or ACTIVE state
            if negative_constraint:
                cur.execute("""
                    INSERT INTO agent_lessons
                    (source_issue_id, topic_tag, rule_instruction, negative_constraint, priority_score, is_active, verified_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (issue_id, category, correction, negative_constraint, 7, False, 'PENDING_REVIEW'))

            conn.commit()
    except Exception as e:
        logger.warning(f"Could not persist agent_issues: {e}")
    return issue_id

async def enqueue_post_call_critique(customer_phone: str, call_history: list, direction: str = "INBOUND", call_id: str = None):
    """
    Asynchronous non-blocking entry point called by the telephony pipeline.
    """
    import asyncio
    try:
        await asyncio.to_thread(run_multi_signal_audit, customer_phone, call_history, direction, call_id or f"call_{customer_phone}")
    except Exception as e:
        logger.error(f"Error in async post-call critique: {e}")
