**Subject: Inbound calls to 917943446755 never reach our AI agent (silence, no CDR) — please check inbound provisioning**

Hello TeleCMI / PIOPIY team,

Account: **Qala Labs** (dashboard.piopiy.com)
Number: **917943446755** (status: Enabled)
App / AI agent: **AirborneAviation** — ID `edc5b96c-9e10-4b1f-b2b0-528da3c30978`
Agent data-center region: **Delhi (India)** (set on 15 Oct 2026)

**Problem**
Inbound calls to 917943446755 from a normal mobile phone never reach our AI agent. The caller hears nothing (silence; earlier attempts gave a "server unreachable" tone). No inbound call is recorded anywhere on your side or ours.

**Evidence**
- The number's Forward setting points to the app *AirborneAviation*, whose ID matches our worker's agent ID. The agent is Enabled, and our worker is connected to your signaling server as that agent (logs show "Connected to signaling as agent edc5b96c-…" on every start).
- The agent's call log (Oct 9–15, 2026) lists 32 calls, **all outbound** from 917943446755 to customers (the latest on 12 Oct 2026). **There is not a single inbound record**, including today's test calls on 15 Oct 2026 (morning, IST — please fill in the exact time you called).
- Our server received no request and no call-session event for those inbound attempts, so the call is being stopped before it reaches the agent.
- Outbound calls from the same number and agent work (connected calls on 9, 10 and 12 Oct 2026).

**New finding (15 Oct 2026, ~11:16 IST):** an outbound call placed through your API for the same agent (caller_id 917943446755 → 916006760151) was rejected with the error **`kyc_not_verified`** (both `ai.call` and the `pcmo.call` fallback). Outbound calls from this account worked on 9, 10 and 12 Oct 2026, so the account KYC status appears to have changed, or the KYC for this number is not verified. This may also be why inbound calls are not delivered.

**What we need from you**
0. **Please check the KYC status of the Qala Labs account and of number 917943446755, tell us exactly what is missing or expired, and verify/re-verify it.** We can upload any documents you need immediately.
1. Is 917943446755 a voice number that accepts **inbound calls from mobile/PSTN networks**? Or is it provisioned for outbound caller-ID only (it looks like an Ahmedabad 079 landline-style number)?
2. If inbound is not enabled, please enable it and tell us if any plan, KYC or additional documents are needed.
3. Please confirm the number is routed to the AI agent app *AirborneAviation* for inbound calls, and whether any other setting (for example inbound channel capacity for India) must be configured.
4. Please check your switch logs for inbound attempts to 917943446755 on 15 Oct 2026 (morning IST — exact call time to be added) and tell us the rejection reason.
5. If this number cannot receive inbound calls, please provide an alternative inbound number we can attach to the same agent.

Please also confirm that call status events are delivered to our Debug/Event URL (`https://airborne-voice-assistant-368523757732.asia-south1.run.app/telecmi/events`); we have received none since 28 Sep 2026.

Thank you. Happy to join a call or provide more logs.

Regards,
Qala Labs — Airborne Aviation AI voice assistant
