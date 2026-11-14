"""
VAGADK Google ADK Agent Definition
Constructs the in-process Google ADK Agent for Airborne Aviation Academy live telephony dialogue.
"""

import sys
import os
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
from adk_core.tools import search_knowledge, book_counseling_session

try:
    from learning.lesson_injector import get_active_lessons_prompt
except ImportError:
    def get_active_lessons_prompt(phone: str = "") -> str:
        return ""

# Google ADK & GenAI imports
try:
    from google.adk import Agent
    from google.genai import types
except ImportError:
    Agent = None
    types = None

BASE_TELEPHONY_INSTRUCTION = """You are Piyush, the Senior Admissions Counselor and Flight Training Advisor at Airborne Aviation Academy, Ramphal Chowk, Sector 7, Dwarka, New Delhi.
Captain Navrang Singh is our Chief Pilot Instructor & Head of Training who personally leads the DGCA ground classes and Airbus A320 simulator sessions.
You are speaking live on a telephone call with a prospective student or parent.

CORE TELEPHONY RULES:
1. Turn Pacing & Brevity: Keep every turn strictly to 2-3 short, natural phone sentences. Avoid monologues.
2. Language Mirroring: If the caller speaks English, reply in natural, professional English. If the caller speaks Hindi or Hinglish, reply in warm, fluent Hinglish.
3. Currency Normalization: Always state currency as 'Rs.' or 'Rupees' (NEVER use the symbol '₹').
4. Ground Truth: Airborne Aviation Academy is led by Captain Navrang Singh at Ramphal Chowk, Dwarka, New Delhi. Ground classes cover DGCA CPL exams (Air Navigation, Meteorology, Air Regulations, Technical General, and RTR). Full flying training is ~Rs. 55-65 Lakhs (200 hours). Ground classes tuition is Rs. 2,70,000.
5. Knowledge Lookup: Always use the search_knowledge tool whenever asked about specific fees, eligibility, syllabus, or medical rules to ensure 100% factual accuracy.
6. Booking Consultations: When a student expresses interest in visiting the campus, trying the A320 simulator, or meeting Captain Navrang Singh, offer to book a consultation using the book_counseling_session tool.
7. Ending Calls: If the caller says goodbye, thanks you, or wants to hang up, provide a warm closing and append [EXIT].
"""

def build_telephony_adk_agent(
    customer_phone: str = "",
    custom_instructions: Optional[str] = None
):
    """
    Constructs an in-process Google ADK Agent instance pre-loaded with:
    1. Base telephony counselor persona (Piyush)
    2. Dynamic negative constraints / lessons learned from past calls
    3. Low-latency voice configuration (thinking_budget: 0)
    4. RAG search tool & booking tool
    """
    if Agent is None or types is None:
        raise RuntimeError("Google ADK or google-genai is not installed in the environment.")

    # Ensure GEMINI_API_KEY / GOOGLE_API_KEY is available in os.environ for google-genai
    if getattr(config, "GEMINI_API_KEY", None):
        if not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = config.GEMINI_API_KEY
        if not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = config.GEMINI_API_KEY

    # 1. Fetch dynamic lessons learned from Critic/DB
    dynamic_lessons = get_active_lessons_prompt(customer_phone)

    # 2. Combine instructions
    instruction_parts = [custom_instructions or BASE_TELEPHONY_INSTRUCTION]
    if dynamic_lessons:
        instruction_parts.append(f"\n\n{dynamic_lessons}")

    full_instruction = "\n".join(instruction_parts)

    # 3. Model & generation config with zero thinking budget for sub-second voice pacing
    model_name = getattr(config, "GEMINI_MODEL", "gemini-3.1-flash-lite") or "gemini-3.1-flash-lite"

    # Configure low latency voice parameters
    content_config = types.GenerateContentConfig(
        temperature=0.3,
        max_output_tokens=75,
        thinking_config=types.ThinkingConfig(thinking_budget=0)
    )

    agent = Agent(
        name="airborne_telephony_agent",
        model=model_name,
        instruction=full_instruction,
        tools=[search_knowledge, book_counseling_session],
        generate_content_config=content_config
    )

    return agent
