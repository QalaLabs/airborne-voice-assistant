-- =====================================================================
-- VAGADK: Analytical SQL Views for Developer Inspection
-- =====================================================================

-- 1. Unresolved Issues Queue: Everything requiring developer review
CREATE OR REPLACE VIEW vw_unresolved_issues AS
SELECT 
    id,
    call_id,
    customer_phone,
    direction,
    mistake_category,
    severity,
    caller_utterance,
    agent_response,
    critic_reasoning,
    suggested_correction,
    proposed_negative_constraint,
    status,
    created_at
FROM agent_issues
WHERE status IN ('PENDING_REVIEW', 'AUTO_APPLIED')
ORDER BY 
    CASE severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END,
    created_at DESC;

-- 2. Active Live Lessons: Negative constraints currently injected into live calls
CREATE OR REPLACE VIEW vw_active_lessons AS
SELECT 
    id,
    source_issue_id,
    topic_tag,
    rule_instruction,
    negative_constraint,
    priority_score,
    verified_by,
    created_at
FROM agent_lessons
WHERE is_active = TRUE
ORDER BY priority_score DESC, created_at DESC;

-- 3. Daily Call Quality & Mistake Summary
CREATE OR REPLACE VIEW vw_daily_quality_summary AS
SELECT 
    DATE(created_at) as call_date,
    COUNT(*) as total_evaluated_calls,
    ROUND(AVG(caller_sentiment_score)::numeric, 2) as avg_sentiment,
    ROUND(AVG(factual_accuracy_score)::numeric, 2) as avg_accuracy,
    SUM(CASE WHEN friction_detected THEN 1 ELSE 0 END) as calls_with_friction,
    SUM(CASE WHEN compliance_passed THEN 1 ELSE 0 END) as fully_compliant_calls
FROM agent_eval_metrics
GROUP BY DATE(created_at)
ORDER BY call_date DESC;
