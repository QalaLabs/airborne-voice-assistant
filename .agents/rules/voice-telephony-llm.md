---
description: Best practices and invariants for real-time voice telephony agents and Gemini LLM integration
globs: ["*.py", "**/*.py"]
---

# Real-Time Voice Telephony & LLM Guidelines

## 1. Gemini Low-Latency Voice Optimization
- **Disable Thinking Budget**: When integrating Gemini 3.8+ models into telephony or conversational streaming pipelines, always specify:
  ```python
  "generationConfig": {
      "thinkingConfig": {"thinkingBudget": 0}
  }
  ```
  This prevents internal reasoning tokens from consuming the token budget or inflating latency.
- **Concatenate All Candidate Parts**: Always join all text parts across response candidates:
  ```python
  text = ''.join([p.get('text', '') for p in parts if 'text' in p])
  ```
- **Flash Model Fallback Chain**: Guard telephony calls against single-model 503/429 spikes by cascading requests across compatible flash models:
  ```python
  fallback_models = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]
  ```

## 2. Character & TTS Audio Normalization
- **Currency Symbols**: Normalize Unicode currency symbols (e.g., `₹`) to `Rs.` or `Rupees` before terminal logging and TTS synthesis. This avoids Windows `cp1252` encoding crashes and produces natural TTS audio.
- **Clean Telephony Output**: Strip control tokens (such as `[EXIT]`) before passing text to speech synthesis.

## 3. Telephony Persona & Language Matching
- **Bilingual Fluency**: Telephony agent prompts in multilingual domains should explicitly instruct the model to detect and mirror the caller's language (fluent English for English queries, Hinglish for Hindi/Hinglish queries).
- **Concise Turn Caps**: Restrict conversational telephony responses to 2–3 short sentences per turn for natural phone pacing.
