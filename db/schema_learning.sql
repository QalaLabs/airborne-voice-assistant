-- =====================================================================
-- VAGADK: Continuous Learning, Mistake Tracking & Evaluation Schema
-- =====================================================================

-- 1. Agent Issues: Detailed audit log of every detected mistake during calls
CREATE TABLE IF NOT EXISTS agent_issues (
    id SERIAL PRIMARY KEY,
    call_id VARCHAR(128),
    customer_phone VARCHAR(32),
    direction VARCHAR(16) DEFAULT 'INBOUND', -- 'INBOUND' or 'OUTBOUND'
    mistake_category VARCHAR(64) NOT NULL,    -- 'FACTUAL_ERROR', 'HALLUCINATION', 'USER_CORRECTION', 'TONE_VIOLATION', 'UNHANDLED_OBJECTION', 'PRICING_ERROR'
    severity VARCHAR(16) DEFAULT 'MEDIUM',    -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    turn_index INT DEFAULT 0,
    caller_utterance TEXT,
    agent_response TEXT,
    critic_reasoning TEXT NOT NULL,
    suggested_correction TEXT NOT NULL,
    proposed_negative_constraint TEXT,
    status VARCHAR(32) DEFAULT 'PENDING_REVIEW', -- 'PENDING_REVIEW', 'AUTO_APPLIED', 'VERIFIED_BY_DEV', 'REJECTED'
    reviewer_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Agent Lessons: Active dynamic prompt constraints injected into live calls
CREATE TABLE IF NOT EXISTS agent_lessons (
    id SERIAL PRIMARY KEY,
    source_issue_id INT REFERENCES agent_issues(id) ON DELETE SET NULL,
    topic_tag VARCHAR(64) DEFAULT 'GENERAL',  -- 'CPL_FEES', 'DGCA_MEDICAL', 'GROUND_CLASSES', 'ELIGIBILITY', 'CADET_PROGRAM', 'GENERAL'
    rule_instruction TEXT NOT NULL,
    negative_constraint TEXT NOT NULL,         -- e.g. "Do NOT claim DGCA Class 1 medical can be done at private clinics."
    priority_score INT DEFAULT 5,              -- 1 (low) to 10 (highest priority prompt rule)
    is_active BOOLEAN DEFAULT TRUE,
    verified_by VARCHAR(64) DEFAULT 'SYSTEM',  -- 'SYSTEM' or developer username
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Agent Evaluation Metrics: Per-call aggregate analytics and scoring
CREATE TABLE IF NOT EXISTS agent_eval_metrics (
    id SERIAL PRIMARY KEY,
    call_id VARCHAR(128) UNIQUE,
    customer_phone VARCHAR(32),
    direction VARCHAR(16),
    caller_sentiment_score FLOAT DEFAULT 0.0, -- -1.0 (very upset) to 1.0 (delighted)
    friction_detected BOOLEAN DEFAULT FALSE,
    friction_type VARCHAR(64),                -- 'CALLER_CORRECTION', 'REPETITION', 'INTERRUPTION', 'EARLY_HANGUP', 'NONE'
    factual_accuracy_score FLOAT DEFAULT 1.0, -- 0.0 to 1.0
    compliance_passed BOOLEAN DEFAULT TRUE,
    total_turns INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Fast Indexing
CREATE INDEX IF NOT EXISTS idx_agent_issues_status ON agent_issues(status);
CREATE INDEX IF NOT EXISTS idx_agent_issues_phone ON agent_issues(customer_phone);
CREATE INDEX IF NOT EXISTS idx_agent_issues_created ON agent_issues(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_lessons_active ON agent_lessons(is_active, priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_agent_lessons_topic ON agent_lessons(topic_tag) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_agent_eval_metrics_call ON agent_eval_metrics(call_id);
