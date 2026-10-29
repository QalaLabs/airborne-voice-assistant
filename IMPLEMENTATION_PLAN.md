# Implementation Plan: Reliable Inbound + Outbound Calls (and security hardening)

Scope: `airborne-voice-assistant` on Cloud Run (`asia-south1`), TeleCMI/PioPiy DID `917948568600`, agent `edc5b96c-…`.

## 0. What the code already tells us (corrects the earlier report)

| Earlier claim | What the repo shows | Consequence |
|---|---|---|
| Cloud Run throttles CPU / may have 0 instances | `deploy.ps1:44-46` already sets `--min-instances 1 --no-cpu-throttling` | Not the cause. Drop "Root Cause 1.2". The real instance risk is `--max-instances 10` (stateful worker, see P2). |
| Inbound fails because webhook URL is wrong in portal | Zero hits on `/telecmi/answer` is equally consistent with the DID being bound **directly to the AI agent** (no webhook step) or unbound. | Unproven. Must be verified in the TeleCMI portal + a test call before any code change (Phase 1). |
| `call_queued` → phone never rang is a DND/CLI issue | Also unproven. `main.py:595-615` shows inbound returns `connect → agent`, outbound uses `client.ai.call` (`telephony.py:126`). | Need CDR/status evidence per call (Phase 2). |
| Revision skew (00038 deployed before commit 0a79591) | Plausible; only affects test-lead data, not carrier routing. | Deploy once at the end of each phase, record the git SHA in the revision. |
| Low-latency VAD "constantly aborts TTS" | Speculative. | Test only after connectivity works (Phase 5). |

Rule for this plan: **no fix ships without evidence for its cause.** Phase 1 produces that evidence.

## Phase 1: Prove where inbound and outbound break (no code risk)

1. Portal check (done: DID is bound directly to the AI agent). Still to confirm: agent `edc5b96c…` shows Active, and the Debug/Event URL points to `/telecmi/events`.
2. Place one inbound call from a non-test mobile. Immediately read Cloud Run logs for the window. Outcomes:
   - Worker logs "Call session connected" → routing is fine; failure is inside `create_session`/audio pipeline.
   - No worker session log, signaling connected → agent/DID not matched in PioPiy; raise with TeleCMI support with the call time.
   - No worker session log, signaling disconnected → worker outage (Phase 2).
3. Outbound: for 3 calls (test numbers + one real consenting number), capture the `call_queued` request id and match it to TeleCMI CDR / `/telecmi/events` payloads. Record: ringing? answered? failure code (DND, CLI, busy).
4. Verify worker liveness: `piopiy_agent_worker.py` signaling socket connected at call time (log lines around "Connecting to Piopiy signaling server"). Confirm the 10:19:58 "packet queue is empty" drop and the ~16 s offline window; any call in that window fails.

Exit gate: a written one-line root cause for inbound and for outbound, each backed by a log/CDR line.

### Phase 1 results (Cloud Run logs, read 2026-10-15, project `airborne-aviation-505100`)

- **Inbound: zero real inbound calls reached the worker in 30 days.** Only two `Call session connected` lines exist (2026-10-09 22:03 and 2026-10-12 00:28), both outbound to the test number +916006760151. Because the DID is bound to the agent, an inbound call must produce that line; none did. Either nobody real has called since the binding, or the carrier never delivers to the agent. Needs one controlled inbound test while watching logs.
- **Outbound: `call_queued` does not mean connected.** Dispatches on 10-09 21:10, 21:16, 21:58, 10-10 02:55, 03:50 and 10-12 00:29 were all `call_queued`; only two sessions followed. After the 10-10 03:51 and 10-12 00:29 dispatches there is no worker session, no event and no error: the call never reached the agent and nothing in our logs says why.
- **No delivery feedback:** `/telecmi/events` last received data on 2026-09-28. There is no call status being sent back, so ring/answer/fail is invisible. Confirm the Debug/Event URL in the portal (and set `TELECMI_WEBHOOK_TOKEN`).
- **Worker connection is flaky but recovers:** signaling reconnected 10-14 at 08:26, 09:21 and 10:20; at 10:19:58 `engineio` logged "packet queue is empty, aborting" and the agent was offline about 16 s. A 08:21 request was aborted with "no available instance".
- **Revision skew claim is outdated:** revision `00039` was deployed 10-12 00:28, after commit `0a79591`.
- **Dispatch endpoint was reachable unauthenticated:** `POST /api/calls/dispatch` returned 200 with no credentials (10-12 00:29). Now fixed in code (not yet deployed).
- **Cannot be read from these logs:** the PSTN leg result (TeleCMI CDR / dashboard call log for request ids `8254dce8…` and `22d21d5a…` will show the real failure reason).

## Phase 2: Make the worker survive and be observable

1. Set `--max-instances 1` in `deploy.ps1` and `deploy.sh` (dossiers, cached audio, scheduler jobs are per-instance memory; a 2nd instance means calls land on a worker with no dossier). Keep `min-instances 1`.
2. Worker health: add reconnect-with-backoff around the signaling connection and a `/healthz` that reports signaling-connected, not just process-up. Alert (Cloud Monitoring log-based metric) when disconnected > 10 s.
3. Remove blocking DB calls from the live event loop: wrap `get_dossier`/`get_lead_by_phone`/history saves used from `create_session` in `asyncio.to_thread` (or async driver). Likely contributor to the signaling drop.
4. Bake the Whisper model into the Docker image (`Dockerfile`) and set `HF_HUB_OFFLINE=1` to cut the ~25 s cold start that caused the "no available instance" abort.
5. Fix `precall_manager.py:~411` `asyncio.run` in a thread against the shared ElevenLabs client: create the client per-thread or use `run_coroutine_threadsafe` on the main loop; close old clients.
6. Bound caches: LRU/TTL (e.g. 200 entries, 1 h) for prewarmed audio and dossiers.

## Phase 3: Outbound reliability

1. Persist every dispatch: store `request_id`, phone, timestamp, status in the DB at `telephony.py:126`.
2. Status tracking from `/telecmi/events`: map events to `RINGING / ANSWERED / FAILED(code) / NO_ANSWER`; update the row. Treat `call_queued` as `QUEUED` only.
3. Verification timer: if no RINGING within ~8 s, mark `UNCONFIRMED`, alert, and (config flag, default off) retry once via `client.pcmo.call` fallback already present at `telephony.py:137`. Do not auto-fallback to Twilio until Twilio creds exist in prod (none set today).
4. CLI/DND: use the CLI/format that the CDR evidence from Phase 1 supports (do not guess `079…` variants). Add DND/NCPR check before dispatch if TRAI scrubbing applies to this use case (confirm with TeleCMI support).
5. Scheduler (`scheduler.py:27`): skip statuses NOT_INTERESTED, INVALID_NUMBER, DND, CONVERTED, not just "Resolved"; add max-attempts and calling-hours (IST) window. Move the 2-minute call jobs to a durable store (DB table polled by one worker) so restarts do not drop them.

## Phase 4: Inbound correctness

**Confirmed by you: the DID is bound directly to the AI agent.** So `/telecmi/answer` is never called for inbound; the `main.py:517-636` inbound branch (greeting, dossier, CRM save) is dead code for that path, and every inbound call depends entirely on the worker (`piopiy_agent_worker.py`) being connected to the PioPiy signaling server at that instant. The earlier "wrong webhook URL" theory is dropped. Inbound failure now means one of: worker offline/reconnecting, agent not Active, or `create_session` erroring/stalling.

1. Treat the worker as the only inbound path: Phase 2 (reconnect with backoff, health based on signaling state, non-blocking DB) is the primary inbound fix. Add an alert on "signaling disconnected" and a startup log line per registered agent id.
2. `create_session` (`piopiy_agent_worker.py:457-570`): the dossier lookup at line 492 is synchronous (`precall_manager.manager.get_dossier`) and runs before the greeting; wrap in `asyncio.to_thread` with a ~1.5 s timeout and fall back to the generic inbound dossier so the caller never hears silence.
3. Direction detection (`resolve_call_context`, lines 398-455) defaults to inbound when unsure; log the raw context payload once per call so misclassification of outbound-as-inbound can be seen.
4. Delete or clearly mark the inbound branch of `/telecmi/answer` as legacy fallback (keep it only if you may switch the DID to Answer URL later); if kept, make it fail-safe: on any exception return a PCMO that still `connect`s to the agent (currently `main.py:636` returns a bare `play`, which plays audio and hangs up).
3. Replace the hardcoded test-lead matching (`piopiy_agent_worker.py:439-453`, `505-531`: substrings "7062", "0151", "1143", "deepak", "aayush" over the whole payload/room name) with exact normalized-phone equality against an allowlist from config/DB (`TEST_LEADS`). Real callers must never match by substring.
4. Caller number extraction: use the same normalizer as `precall_manager` (one function), not the ad-hoc list at `main.py:545-565`.

## Phase 5: Security (do before exposing more traffic)

1. Add shared-secret auth (`X-API-Key`, constant-time compare, secret in Secret Manager) to `/api/calls/dispatch`, `/api/calls/prefeed` (POST and GET), `/webhooks/new-lead`. Update `call_with_prefeed.py`, `batch_campaign_dialer.py`, and the CRM/webhook sender to send it.
2. Set `TELECMI_WEBHOOK_TOKEN` in prod and configure `?token=` on the Debug URL (`main.py:746` already validates it). If the portal cannot send it, add IP allowlisting instead.
3. Recording download (`storage_service.py:90`, `voice_test.py:30`): allowlist hostnames (TeleCMI/Twilio only), https only, block private/link-local ranges, send Twilio creds only to `api.twilio.com`; make the bucket objects private with signed URLs.
4. `deploy.ps1/.sh`: stop inlining IDs in `--set-env-vars` where they are credentials-adjacent (ElevenLabs key id), move to Secret Manager; pin `requirements.txt`.
5. Grant the Vertex AI role to the service account and add an alert on Gemini 401/402 so billing lapses do not silently mute the agent.

## Phase 6: Tests and release gate

1. Unit: phone normalization, test-lead exact-match, scheduler eligibility, PCMO responses (success + exception path), auth middleware (401/200).
2. Integration (mock TeleCMI): dispatch → events → status transitions; verification-timer path.
3. Make tests not touch the real DB (`DATABASE_URL` guard); run schema then migrations independently so a schema failure does not skip migrations.
4. Add CI (GitHub Actions: pytest + ruff) and a pre-deploy test gate in `deploy.ps1`/`deploy.sh`; tag each deploy with the git SHA.
5. Acceptance (manual, after deploy): 3 inbound (known lead, unknown caller, caller during worker restart) and 3 outbound (answered, declined, unreachable) calls; each must produce correct CDR status, a conversation row, and no cross-contamination with test leads.

## Order and effort

| Order | Phase | Effort | Risk if skipped |
|---|---|---|---|
| 1 | Phase 1 diagnosis | 1-2 h | Fixing the wrong thing |
| 2 | Phase 5.1-5.2 auth | 2-3 h | Anyone can place calls / read lead data |
| 3 | Phase 4.3 test-lead matching | 1 h | Real callers hijacked |
| 4 | Phase 2 stability | 1 day | Dropped signaling, lost jobs |
| 5 | Phase 3 outbound tracking | 1 day | Silent non-delivery |
| 6 | Phase 4.1-4.2, 4.4 inbound | 0.5 day | Depends on Phase 1 |
| 7 | Phase 5.3-5.5, Phase 6 | 1-2 days | Hardening / regressions |

## Open questions for you

1. What does the TeleCMI portal currently show for the DID's routing (agent vs Answer URL)?
2. Do you want Twilio as a real fallback carrier (needs account + creds), or TeleCMI-only with retries?
3. Is the calling use case registered for TRAI DLT/DND scrubbing?
4. OK to set `max-instances 1` (limits concurrent calls to one container's capacity)?
