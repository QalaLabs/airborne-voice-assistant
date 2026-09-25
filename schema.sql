-- =========================================================
-- Airborne Aviation AI Voice Agent & CRM PostgreSQL Schema
-- =========================================================

-- Enable pgvector extension for RAG semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- Organizations table for CRM tenancy
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) DEFAULT 'Airborne Aviation Academy',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Leads table (supports both CRM Prisma schema and voice agent fields)
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "orgId" UUID,
    name VARCHAR(255),
    phone VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255),
    "courseInterest" VARCHAR(255),
    course_interest VARCHAR(255),
    budget_status VARCHAR(255),
    timeline_urgency VARCHAR(255),
    status VARCHAR(50) DEFAULT 'NEW',
    classification VARCHAR(50) DEFAULT 'Cold',
    source VARCHAR(50) DEFAULT 'VOICE_AGENT',
    metadata JSONB DEFAULT '{}'::jsonb,
    "lastActivityAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    "nextFollowUp" TIMESTAMP WITH TIME ZONE,
    "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Lead activities table for logging call recordings, transcripts, and follow-ups
CREATE TABLE IF NOT EXISTS lead_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "leadId" UUID REFERENCES leads(id) ON DELETE SET NULL,
    "orgId" UUID,
    "activityType" VARCHAR(50) DEFAULT 'CALL',
    title VARCHAR(255),
    notes TEXT,
    outcome VARCHAR(50),
    "dueAt" TIMESTAMP WITH TIME ZONE,
    "completedAt" TIMESTAMP WITH TIME ZONE,
    "durationMins" INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Backward-compatible call logging tables
CREATE TABLE IF NOT EXISTS calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    direction VARCHAR(20) NOT NULL,
    duration INTEGER,
    recording_url TEXT,
    transcript TEXT,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS voice_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    direction VARCHAR(20),
    duration INTEGER,
    recording_url TEXT,
    transcript TEXT,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table to store in-progress call conversation state across Cloud Run instances
CREATE TABLE IF NOT EXISTS conversation_sessions (
    phone VARCHAR(50) PRIMARY KEY,
    direction VARCHAR(20),
    history JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(50) DEFAULT 'ACTIVE',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table to store scraped website text embeddings (1536 dimensions for OpenAI/Gemini)
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding VECTOR(1536)
);

-- Index for HNSW similarity search on embeddings
CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents 
USING hnsw (embedding vector_cosine_ops);

-- Database function for RAG semantic search matching
CREATE OR REPLACE FUNCTION match_documents (
  query_embedding VECTOR(1536),
  match_threshold FLOAT,
  match_count INT
)
RETURNS TABLE (
  id BIGINT,
  content TEXT,
  metadata JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    documents.id,
    documents.content,
    documents.metadata,
    1 - (documents.embedding <=> query_embedding) AS similarity
  FROM documents
  WHERE 1 - (documents.embedding <=> query_embedding) > match_threshold
  ORDER BY documents.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
