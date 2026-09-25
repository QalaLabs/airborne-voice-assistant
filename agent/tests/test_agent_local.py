"""
Scripted multi-turn smoke test against the DEPLOYED Agent Engine agent,
mirroring the repo root's test_call_local.py:run_automated_demo_call pattern
but targeting the new backend via agent_client.query_agent() instead of
gpt_test.chat_with_gpt().

This is a manual-inspection smoke test, not an automated pass/fail suite --
read the printed responses for tone/accuracy/"[EXIT]" correctness per the
plan's verification steps. Run this only after the agent is deployed
(agent/deploy_agent.sh) and AGENT_ENGINE_RESOURCE_NAME/GCP_PROJECT/
GCP_LOCATION are set in the environment.

Usage:
    cd /home/user/airborne-voice-assistant
    python -m agent.tests.test_agent_local
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import config
import agent_client

DIALOGUE_SCRIPT = [
    "Hi Modassir sir, I want to know about DGCA CPL Ground Classes fees and duration.",
    "That sounds great. Can I visit the campus in Dwarka this Saturday to see the A320 simulator?",
    "Yes, Saturday 11 AM works for me. Thank you, Modassir sir! Bye.",
]


def run_scripted_smoke_test(phone: str = "+919876543210"):
    if not config.AGENT_ENGINE_RESOURCE_NAME:
        print("config.AGENT_ENGINE_RESOURCE_NAME is not set. Deploy the agent first "
              "(agent/deploy_agent.sh) and set that env var before running this test.")
        return

    print("=" * 65)
    print("  AGENT ENGINE SCRIPTED SMOKE TEST")
    print("=" * 65)

    history = []
    for turn_idx, user_speech in enumerate(DIALOGUE_SCRIPT, 1):
        print(f"\n--- Turn {turn_idx} ---")
        print(f"Lead: \"{user_speech}\"")

        try:
            ai_response = agent_client.query_agent(user_speech, history, phone)
        except Exception as e:
            print(f"[FAILED] Agent Engine call raised: {e}")
            return

        print(f"Agent: \"{ai_response.replace('[EXIT]', '').strip()}\"")
        history.append({"role": "user", "content": user_speech})
        history.append({"role": "assistant", "content": ai_response})

        if "[EXIT]" in ai_response.upper():
            print("\n[Call would end here -- '[EXIT]' token present]")
            break

    print("\n" + "=" * 65)
    print("Manually verify above: persona/tone, tool-call correctness for the "
          "fee question, sentence-length discipline, and '[EXIT]' on the final turn.")
    print("=" * 65)


if __name__ == "__main__":
    phone_arg = sys.argv[1] if len(sys.argv) > 1 else "+919876543210"
    run_scripted_smoke_test(phone=phone_arg)
