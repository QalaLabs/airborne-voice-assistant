---
description: Critical guardrails for Piopiy AI Telephony workers, LiveKit WebRTC, and voice pipeline services
globs: "**/piopiy_agent_worker.py, **/telephony.py, **/main.py, **/*voice*"
---

# Piopiy AI Telephony Guardrails

When modifying, developing, or running voice agents and telephony workers:

1. **Daemon Lifecycle & Duplicate Identity**:
   - Never run multiple instances of `piopiy_agent_worker.py` simultaneously. LiveKit will immediately disconnect calls with `DuplicateIdentity`.
   - Always terminate stale background processes (`Stop-Process -Name python3.13, py -Force`) before starting a new worker.

2. **Windows Unicode & Audio Text Invariants**:
   - Set `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` at the very top of worker scripts.
   - In system instructions for voice agents, instruct the LLM to write currency values phonetically (e.g., "Rupees", "Lakhs", "Rs.") rather than using Unicode symbols like `₹` to avoid Windows charmap encoding crashes and robotic TTS pronunciation.

3. **Gemini Voice Models**:
   - Use `gemini-3.8-flash` or `gemini-flash-latest`. Avoid deprecated models (`gemini-2.5-flash`, `gemini-2.0-flash`) which throw 404 NOT_FOUND.

4. **Whisper STT Hardware Fallback**:
   - Always specify `device="cpu", compute_type="int8"` on Windows systems where CUDA `cublas64_12.dll` is not guaranteed.

5. **Telephony Carrier Dispatch & Delivery Verification**:
   - **`call_queued` != Delivery**: Carrier APIs (TeleCMI/PioPiy `client.ai.call()`) returning `call_queued` only indicates receipt by the message broker, not PSTN connection. Always verify PSTN leg status via CDR/webhook events and maintain a secondary fallback carrier (Twilio or standard PCMO) if ringing does not initiate within 6 seconds.
   - **DID Inbound Routing Alignment**: When changing inbound call logic between WebRTC agent bridges and PCMO HTTP webhooks, verify that the carrier virtual number (DID) route in the portal points to the active Cloud Run `/telecmi/answer` endpoint rather than stale SIP trunk or static IVR configs.

6. **Low-Latency & Weaker Network Audio Guardrails**:
   - **Barge-in Grace Window**: In low-bandwidth cellular environments, always enforce an initial 1.0–1.5s grace period before activating microphone interruption detection (`allow_interruptions`). Cellular ring-trip clicks and carrier audio spikes will otherwise falsely trigger VAD and cancel greeting playback before the caller hears the agent.
   - **Container Deployment Synchronization**: Cloud Run containers must be re-deployed immediately following any pre-call logic or routing updates to prevent divergence between git HEAD and live container revisions.
