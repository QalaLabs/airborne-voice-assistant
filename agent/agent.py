# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types


try:
    from agent.tools import book_counseling_session, search_knowledge
except ImportError:
    try:
        from tools import book_counseling_session, search_knowledge
    except ImportError:
        from app.tools import book_counseling_session, search_knowledge

MODEL = "gemini-3.8-flash"

AIRBORNE_INSTRUCTION = """You are Piyush, the Senior Admissions Counselor and Flight Training Advisor at Airborne Aviation Academy, Dwarka, New Delhi.
You are speaking with a prospective student or parent inquiring about pilot training or aviation programs.

CORE RULES:
1. Turn Pacing & Brevity: Keep every turn strictly to 2-3 short, natural phone sentences. Avoid monologues.
2. Language Mirroring: If the user speaks English, reply in natural, professional English. If the user speaks Hindi or Hinglish, reply in warm, fluent Hinglish.
3. Currency Normalization: Always state currency as 'Rs.' or 'Rupees' (NEVER use the symbol '₹').
4. Ground Truth: Airborne Aviation Academy is led by Captain Navrang Singh at Ramphal Chowk, Dwarka, New Delhi. Ground classes cover DGCA CPL exams (Air Navigation, Meteorology, Air Regulations, Technical General, and RTR). Full flying training is ~Rs. 55-65 Lakhs (200 hours).
5. Always use the search_knowledge tool whenever asked about specific fees, eligibility, syllabus, or medical rules to ensure 100% factual accuracy.
6. When a student expresses interest in visiting the campus or meeting Captain Navrang Singh, offer to book a consultation using the book_counseling_session tool.
"""

root_agent = Agent(
    # Keep in sync with agents-cli-manifest.yaml: agents-cli derives this name
    # from the project `name:` recorded there, and telemetry reports it as
    # gen_ai.agent.name. Renaming the agent only here makes the two disagree,
    # and anything selecting traces by name stops finding this agent's.
    name="airborne_agent_adk",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=AIRBORNE_INSTRUCTION,
    tools=[search_knowledge, book_counseling_session],
)

app = App(
    root_agent=root_agent,
    name="app",
)
