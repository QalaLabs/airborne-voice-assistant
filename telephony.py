import os
import requests
import threading
import time
import config
import database
import supabase_client

MAX_CONCURRENT_CALLS = 2
_active_calls_lock = threading.Lock()
_active_calls = {}

CALL_VERIFICATION_TIMEOUT_SECS = float(os.getenv("CALL_VERIFICATION_TIMEOUT_SECS", "6.0"))
FORCE_PCMO_OUTBOUND = os.getenv("FORCE_PCMO_OUTBOUND", "false").lower() in ("1", "true", "yes")

_dispatched_calls_lock = threading.Lock()
_dispatched_calls = {}
_phone_to_req = {}
_active_watchers = {}

def get_dispatched_call_status(identifier: str) -> dict:
    """Returns current delivery status for request_id or phone."""
    with _dispatched_calls_lock:
        digits = "".join(filter(str.isdigit, identifier))
        if identifier in _dispatched_calls:
            return dict(_dispatched_calls[identifier])
        if digits in _phone_to_req:
            req_id = _phone_to_req[digits]
            return dict(_dispatched_calls.get(req_id, {}))
        return {}

def cancel_all_watchers():
    """Cancels all active delivery verification timers (useful in tests and shutdown)."""
    with _dispatched_calls_lock:
        for timer in list(_active_watchers.values()):
            try:
                if timer and timer.is_alive():
                    timer.cancel()
            except Exception:
                pass
        _active_watchers.clear()

def mark_call_progress(identifier: str, status: str, call_id: str = None):
    """
    Updates delivery status of an outbound call (e.g. RINGING, CONNECTED, ANSWERED, COMPLETED).
    Satisfies or cancels the delivery verification watcher so stalled queue alerts or fallbacks
    do not misfire once a call is actively ringing or connected.
    """
    with _dispatched_calls_lock:
        digits = "".join(filter(str.isdigit, identifier))
        req_id = identifier if identifier in _dispatched_calls else _phone_to_req.get(digits)
        if req_id and req_id in _dispatched_calls:
            entry = _dispatched_calls[req_id]
            old_status = entry.get("status")
            entry["status"] = status.upper()
            if call_id:
                entry["call_id"] = call_id
            entry["updated_at"] = time.time()
            print(f"Telephony: Call progress updated for {entry.get('phone')} (req={req_id}): {old_status} -> {status.upper()}")

            # If moving to active or terminal status, cancel any pending watcher
            if status.upper() in ("RINGING", "CONNECTED", "ANSWERED", "IN_PROGRESS", "COMPLETED", "HANGUP", "FAILED", "BUSY", "NO_ANSWER", "REJECTED"):
                timer = _active_watchers.pop(req_id, None)
                if timer and timer.is_alive():
                    timer.cancel()

    # If terminal status, ensure active call slot is released
    if status.upper() in ("COMPLETED", "HANGUP", "FAILED", "REJECTED", "BUSY", "NO_ANSWER", "DND"):
        release_active_call(identifier)

def _execute_pcmo_fallback(parent_request_id: str, formatted_phone: str, lead_name: str, precall_data: dict):
    """
    Emergency recovery dial: bypasses the stalled AI agent message broker queue and dials
    the PSTN handset directly via client.pcmo.call with an agent connect pipeline.
    """
    try:
        app_id = (
            getattr(config, "AGENT_ID", "")
            or config.TELECMI_PIOPIY_APP_ID
            or config.TELECMI_APP_ID
        )
        token = getattr(config, "AGENT_TOKEN", "") or config.TELECMI_TOKEN or ""
        if not (token and app_id):
            print("Telephony: Fallback failed: missing token or app_id.")
            return

        from piopiy.voice import RestClient
        client = RestClient(token=token)
        raw_caller = "".join(filter(str.isdigit, str(config.TELECMI_PHONE_NUMBER or "")))
        caller_id = "91" + raw_caller if len(raw_caller) == 10 else raw_caller
        clean_digits = "".join(filter(str.isdigit, formatted_phone))
        telecmi_to = clean_digits if not clean_digits.startswith("+") else clean_digits[1:]
        if len(telecmi_to) == 10:
            telecmi_to = "91" + telecmi_to

        pipeline = [
            {
                "action": "connect",
                "params": {
                    "caller_id": caller_id
                },
                "endpoints": [
                    {
                        "type": "agent",
                        "id": app_id
                    }
                ]
            }
        ]

        print(f"Telephony: [AUTO-RECOVERY] Dispatching direct PCMO call to {telecmi_to} (caller_id={caller_id}, agent={app_id})...")
        res = client.pcmo.call(
            caller_id=caller_id,
            to_number=telecmi_to,
            app_id=app_id,
            pipeline=pipeline
        )
        print(f"Telephony: PioPiy PCMO fallback call dispatched: {res}")
        body_err = _response_error(res)
        if body_err:
            raise RuntimeError(body_err)

        fallback_req = res.get("request") if isinstance(res, dict) and res.get("request") else f"fallback-{int(time.time())}"
        with _dispatched_calls_lock:
            if parent_request_id in _dispatched_calls:
                _dispatched_calls[parent_request_id]["status"] = "FALLBACK_PCMO_DISPATCHED"
                _dispatched_calls[parent_request_id]["fallback_request_id"] = fallback_req
            _dispatched_calls[fallback_req] = {
                "phone": formatted_phone,
                "status": "QUEUED",
                "dispatched_at": time.time(),
                "provider": "piopiy_pcmo_fallback",
                "parent_request_id": parent_request_id
            }
            digits = "".join(filter(str.isdigit, formatted_phone))
            _phone_to_req[digits] = fallback_req

        # Secondary 8-second check on fallback
        def _secondary_check():
            with _dispatched_calls_lock:
                entry = _dispatched_calls.get(fallback_req)
                status = entry.get("status") if entry else None
            if status == "QUEUED":
                print(f"Telephony: [ALERT] Secondary PCMO fallback to {formatted_phone} also stalled in queue. Marking STALLED_CARRIER_OR_DND.")
                mark_call_progress(formatted_phone, "STALLED_CARRIER_OR_DND")
                release_active_call(formatted_phone)

        sec_timer = threading.Timer(8.0, _secondary_check)
        sec_timer.daemon = True
        sec_timer.start()

    except Exception as e:
        print(f"Telephony Error: Automatic PCMO fallback failed: {e}")
        mark_call_progress(formatted_phone, "FALLBACK_FAILED")
        release_active_call(formatted_phone)

def _schedule_delivery_verification(request_id: str, formatted_phone: str, lead_name: str, precall_data: dict, timeout_secs: float = CALL_VERIFICATION_TIMEOUT_SECS):
    """
    Starts an asynchronous background verification timer.
    If the carrier message broker returned 'call_queued' but no ringing, bridge,
    or session connected event arrives within timeout_secs, triggers automatic PCMO fallback.
    """
    if not request_id:
        return

    def _watcher_callback():
        with _dispatched_calls_lock:
            entry = _dispatched_calls.get(request_id)
            if not entry:
                return
            current_status = entry.get("status")

        if current_status == "QUEUED":
            print(f"Telephony: [ALERT] Call to {formatted_phone} (req={request_id}) STALLED in 'call_queued' for {timeout_secs}s without PSTN ringing.")
            print(f"Telephony: [AUTO-RECOVERY] Triggering automatic PCMO dial fallback for {formatted_phone}...")
            _execute_pcmo_fallback(request_id, formatted_phone, lead_name, precall_data)

    timer = threading.Timer(timeout_secs, _watcher_callback)
    timer.daemon = True
    with _dispatched_calls_lock:
        _active_watchers[request_id] = timer
    timer.start()

def get_active_calls_count() -> int:
    """Returns number of active concurrent calls, pruning expired leases (>15 mins)."""
    with _active_calls_lock:
        now = time.time()
        expired = [p for p, t in _active_calls.items() if now - t > 900]
        for p in expired:
            _active_calls.pop(p, None)
        return len(_active_calls)

def register_active_call(phone: str) -> bool:
    """
    Attempts to acquire a call slot under the MAX_CONCURRENT_CALLS (2) limit.
    Returns True if registered, False if concurrency limit is reached.
    """
    with _active_calls_lock:
        now = time.time()
        expired = [p for p, t in _active_calls.items() if now - t > 900]
        for p in expired:
            _active_calls.pop(p, None)
        if len(_active_calls) >= MAX_CONCURRENT_CALLS:
            return False
        _active_calls[phone] = now
        return True

def release_active_call(phone: str):
    """Releases an active call slot when the call concludes or fails."""
    with _active_calls_lock:
        digits = "".join(filter(str.isdigit, phone))
        to_remove = [k for k in _active_calls if k == phone or "".join(filter(str.isdigit, k)) == digits]
        for k in to_remove:
            _active_calls.pop(k, None)

try:
    from twilio.rest import Client
except ImportError:
    Client = None

try:
    import piopiy
except ImportError:
    piopiy = None

def _response_error(res):
    """Returns an error string if a carrier response body signals failure, else None."""
    if isinstance(res, dict):
        status = str(res.get("status", "")).lower()
        if res.get("error"):
            return str(res.get("error"))
        if status in ("error", "failed"):
            return str(res.get("msg") or res.get("message") or res.get("code") or "carrier reported an error")
        code = res.get("code")
        if isinstance(code, int) and code >= 400:
            return str(res.get("msg") or res.get("message") or code)
    return None

def make_outbound_call(phone_number: str, lead_name: str = None, precall_data: dict = None) -> bool:
    """Boolean wrapper around dispatch_outbound_call() for callers that only need success/failure."""
    return dispatch_outbound_call(phone_number, lead_name, precall_data)["ok"]

def dispatch_outbound_call(phone_number: str, lead_name: str = None, precall_data: dict = None) -> dict:
    """
    Triggers an outbound call using PioPiy / TeleCMI (primary) or Twilio (fallback).
    Bridges the call to the FastAPI '/telecmi/answer' or '/answer-call' endpoints.
    Accepts precall_data to pre-feed lead information, pre-warm audio, and eliminate latency.

    Returns {"ok": bool, "provider": str|None, "error": str|None, "request_id": str|None}.
    ok is True only when a carrier accepted the call (or in simulation mode when NO carrier
    credentials are configured); a carrier rejection such as kyc_not_verified yields ok=False.
    """
    errors = []
    carrier_configured = False
    # Normalize phone number (ensure country code)
    clean_digits = "".join(filter(str.isdigit, phone_number))
    if len(clean_digits) == 10:
        formatted_phone = "+91" + clean_digits
        telecmi_to = "91" + clean_digits
    elif clean_digits.startswith("91") and len(clean_digits) == 12:
        formatted_phone = "+" + clean_digits
        telecmi_to = clean_digits
    else:
        formatted_phone = "+" + clean_digits if not phone_number.startswith("+") else phone_number
        telecmi_to = clean_digits
            
    # Enforce concurrency ceiling: maximum 2 calls simultaneously
    if not register_active_call(formatted_phone):
        err = f"Agent concurrency limit reached ({MAX_CONCURRENT_CALLS} concurrent calls). Call rejected."
        print(f"Telephony: {err}")
        return {"ok": False, "provider": None, "error": err, "request_id": None}

    print(f"Telephony: Initiating outbound call to {lead_name or 'Candidate'} at {formatted_phone} (active calls: {get_active_calls_count()}/{MAX_CONCURRENT_CALLS})...")
    
    # 0. Register & pre-warm pre-call context
    import precall_manager
    if precall_data and isinstance(precall_data, dict):
        dossier = precall_manager.manager.register_precall(
            phone=formatted_phone,
            name=lead_name or precall_data.get("name") or "Candidate",
            course_interest=precall_data.get("course_interest") or "Commercial Pilot License (CPL)",
            education=precall_data.get("education"),
            age=precall_data.get("age"),
            city=precall_data.get("city"),
            prior_aviation_exp=precall_data.get("prior_aviation_exp"),
            medicals_status=precall_data.get("medicals_status"),
            budget_or_loan=precall_data.get("budget_or_loan"),
            notes=precall_data.get("notes"),
            call_objective=precall_data.get("call_objective"),
            preferred_language=precall_data.get("preferred_language", "Hinglish"),
            custom_instructions=precall_data.get("custom_instructions"),
            source=precall_data.get("source", "OUTBOUND_CALL"),
            prewarm_audio=True
        )
    else:
        dossier = precall_manager.manager.get_dossier(formatted_phone)
        if not dossier:
            dossier = precall_manager.manager.register_precall(
                phone=formatted_phone,
                name=lead_name or "Candidate",
                source="OUTBOUND_CALL",
                prewarm_audio=True
            )

    # 1. Piopiy PCMO Developer App (Primary using app_id e65072de and Token)
    app_id = (
        getattr(config, "AGENT_ID", "")
        or config.TELECMI_PIOPIY_APP_ID
        or config.TELECMI_APP_ID
    )
    token = getattr(config, "AGENT_TOKEN", "") or config.TELECMI_TOKEN or ""

    if token and app_id:
        carrier_configured = True
        try:
            from piopiy.voice import RestClient
            client = RestClient(token=token)
            raw_caller = "".join(filter(str.isdigit, str(config.TELECMI_PHONE_NUMBER or "")))
            if len(raw_caller) == 10:
                caller_id = "91" + raw_caller
            else:
                caller_id = raw_caller

            # Dynamic personalized greeting audio for the lead
            greeting_text = precall_manager.manager.generate_greeting(dossier, direction="outbound")
            greeting_url = precall_manager.manager.get_prewarmed_audio_url(formatted_phone) or "https://storage.googleapis.com/airborne-aviation-media-prod/tts-audio/greeting_navrang.mp3"
            try:
                import assistant
                if not precall_manager.manager.get_prewarmed_audio_url(formatted_phone):
                    print(f"Telephony: Synthesizing personalized greeting: '{greeting_text}'")
                    greeting_url = assistant.get_greeting_voice_url(greeting_text)
                
                supabase_client.save_conversation_history(
                    formatted_phone,
                    [{"role": "assistant", "content": greeting_text}],
                    "outbound"
                )
            except Exception as ge:
                print(f"Telephony: Notice generating custom greeting ({ge}), using default.")

            base_url = (getattr(config, "APP_URL", "") or getattr(config, "NGROK_URL", "") or "https://airborne-voice-assistant-368523757732.asia-south1.run.app").rstrip("/")
            action_url = f"{base_url}/telecmi/process-recording?phone={telecmi_to}&direction=outbound"
            
            # Agent connect pipeline bridges answered PSTN leg straight to LiveKit agent
            agent_connect_pipeline = [
                {
                    "action": "connect",
                    "params": {
                        "caller_id": caller_id
                    },
                    "endpoints": [
                        {
                            "type": "agent",
                            "id": app_id
                        }
                    ]
                }
            ]
            ivr_fallback_pipeline = [
                {
                    "action": "play_get_input",
                    "prompt": {
                        "type": "file",
                        "file_name": greeting_url
                    },
                    "input": ["speech", "dtmf"],
                    "on_result": {
                        "type": "url",
                        "url": action_url
                    }
                }
            ]
            active_pipeline = agent_connect_pipeline if app_id else ivr_fallback_pipeline

            # Format lightweight variables and call options as specified in Piopiy v3 REST docs
            first_name = (lead_name or (dossier.name if dossier else "Candidate")).strip().split()[0]
            lead_ref = (precall_data.get("lead_id") or precall_data.get("ticket_id") or precall_data.get("id")) if precall_data else None
            ticket_id = str(lead_ref) if lead_ref else f"TCK-{abs(hash(formatted_phone)) % 10000:04d}"

            call_options = {
                "max_duration_sec": 600,
                "record": True,
                "ring_timeout_sec": 40
            }
            call_variables = {
                "customer_name": first_name,
                "ticket_id": ticket_id
            }

            # Optional bypass: If FORCE_PCMO_OUTBOUND is enabled, skip the AI agent queue
            # and dial the PSTN leg directly via PCMO with an immediate agent bridge
            if FORCE_PCMO_OUTBOUND:
                print(f"Telephony: FORCE_PCMO_OUTBOUND is active. Dispatching direct PCMO call to {telecmi_to}...")
                res = client.pcmo.call(
                    caller_id=caller_id,
                    to_number=telecmi_to,
                    app_id=app_id,
                    pipeline=active_pipeline
                )
                print(f"Telephony: PioPiy direct PCMO call dispatched: {res}")
                body_err = _response_error(res)
                if body_err:
                    raise RuntimeError(body_err)
                req_id = res.get("request") if isinstance(res, dict) and res.get("request") else f"req-{int(time.time())}"
                with _dispatched_calls_lock:
                    _dispatched_calls[req_id] = {
                        "phone": formatted_phone,
                        "status": "QUEUED",
                        "dispatched_at": time.time(),
                        "provider": "piopiy_pcmo",
                        "lead_name": lead_name,
                        "precall_data": precall_data
                    }
                    _phone_to_req[clean_digits] = req_id
                return {"ok": True, "provider": "piopiy_pcmo", "error": None,
                        "request_id": req_id, "status": "QUEUED", "verification_active": False}

            print(f"Telephony: Dispatching Piopiy AI call (caller_id={caller_id}, to={telecmi_to}, agent_id={app_id}, vars={call_variables})...")
            try:
                res = client.ai.call(
                    caller_id=caller_id,
                    to_number=telecmi_to,
                    agent_id=app_id,
                    options=call_options,
                    variables=call_variables
                )
                print(f"Telephony: PioPiy AI call dispatched: {res}")
                body_err = _response_error(res)
                if body_err:
                    raise RuntimeError(body_err)

                req_id = res.get("request") if isinstance(res, dict) and res.get("request") else f"req-{int(time.time())}"
                with _dispatched_calls_lock:
                    _dispatched_calls[req_id] = {
                        "phone": formatted_phone,
                        "status": "QUEUED",
                        "dispatched_at": time.time(),
                        "provider": "piopiy_ai",
                        "lead_name": lead_name,
                        "precall_data": precall_data
                    }
                    _phone_to_req[clean_digits] = req_id

                # Arm 6-second delivery verification watcher to rescue queued calls if PSTN leg stalls
                _schedule_delivery_verification(
                    request_id=req_id,
                    formatted_phone=formatted_phone,
                    lead_name=lead_name,
                    precall_data=precall_data,
                    timeout_secs=CALL_VERIFICATION_TIMEOUT_SECS
                )

                return {"ok": True, "provider": "piopiy_ai", "error": None,
                        "request_id": req_id, "status": "QUEUED", "verification_active": True}
            except Exception as ai_err:
                print(f"Telephony: AI call failed ({ai_err}), attempting client.pcmo.call fallback...")
                try:
                    res = client.pcmo.call(
                        caller_id=caller_id,
                        to_number=telecmi_to,
                        app_id=app_id,
                        pipeline=active_pipeline
                    )
                    print(f"Telephony: PioPiy PCMO call dispatched: {res}")
                    body_err = _response_error(res)
                    if body_err:
                        raise RuntimeError(body_err)
                    req_id = res.get("request") if isinstance(res, dict) and res.get("request") else f"req-{int(time.time())}"
                    with _dispatched_calls_lock:
                        _dispatched_calls[req_id] = {
                            "phone": formatted_phone,
                            "status": "QUEUED",
                            "dispatched_at": time.time(),
                            "provider": "piopiy_pcmo",
                            "lead_name": lead_name,
                            "precall_data": precall_data
                        }
                        _phone_to_req[clean_digits] = req_id
                    return {"ok": True, "provider": "piopiy_pcmo", "error": None,
                            "request_id": req_id, "status": "QUEUED", "verification_active": False}
                except Exception as pcmo_err:
                    print(f"Telephony: PCMO dispatch also failed: {pcmo_err}")
                    raise
        except Exception as e:
            print(f"Telephony Error: PioPiy dispatch error: {e}")
            errors.append(str(e))

    # 1b. TeleCMI Legacy REST API fallback
    if config.TELECMI_APP_ID and config.TELECMI_APP_SECRET:
        carrier_configured = True
        try:
            base_url = (getattr(config, "APP_URL", "") or getattr(config, "NGROK_URL", "") or "https://airborne-voice-assistant-hehklcowza-el.a.run.app").rstrip("/")
            answer_url = f"{base_url}/telecmi/answer?direction=outbound&phone={formatted_phone}"
            telecmi_api_url = "https://rest.telecmi.com/v2/make_call"
            
            headers = {
                "Content-Type": "application/json"
            }
            if config.TELECMI_TOKEN:
                headers["Authorization"] = f"Bearer {config.TELECMI_TOKEN}"
                headers["token"] = config.TELECMI_TOKEN
            
            try:
                from_num = int("".join(filter(str.isdigit, str(config.TELECMI_PHONE_NUMBER or ""))))
                to_num = int("".join(filter(str.isdigit, str(telecmi_to))))
            except Exception:
                from_num = config.TELECMI_PHONE_NUMBER or ""
                to_num = telecmi_to

            payload = {
                "appid": config.TELECMI_APP_ID,
                "secret": config.TELECMI_APP_SECRET,
                "from": from_num,
                "to": to_num,
                "answer_url": answer_url
            }
            
            print(f"Telephony: Dispatching TeleCMI REST API call for {formatted_phone}...")
            response = requests.post(telecmi_api_url, json=payload, headers=headers, timeout=10)
            if response.status_code in [200, 201]:
                try:
                    body = response.json()
                except ValueError:
                    body = None
                # TeleCMI reports many failures as HTTP 200 with {"status": "error", "code": ...}.
                body_err = _response_error(body)
                if body_err is None:
                    print(f"Telephony: TeleCMI call initiated successfully: {response.text}")
                    return {"ok": True, "provider": "telecmi_rest", "error": None,
                            "request_id": body.get("request_id") if isinstance(body, dict) else None}
                print(f"Telephony: TeleCMI rejected the call: {response.text}")
                errors.append(body_err)
            else:
                print(f"Telephony: TeleCMI returned HTTP {response.status_code}: {response.text}")
                errors.append(f"HTTP {response.status_code}")
        except Exception as e:
            print(f"Telephony Error: TeleCMI dispatch error: {e}")
            errors.append(str(e))

    # 2. Fallback to Twilio if configured
    if config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and Client:
        carrier_configured = True
        try:
            client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
            twiml_url = f"{config.NGROK_URL}/answer-call?direction=outbound&phone={formatted_phone}"
            
            call = client.calls.create(
                to=formatted_phone,
                from_=config.TWILIO_PHONE_NUMBER,
                url=twiml_url
            )
            print(f"Telephony: Twilio call created successfully. SID: {call.sid}")
            return {"ok": True, "provider": "twilio", "error": None, "request_id": call.sid}
        except Exception as e:
            print(f"Telephony Error: Failed to create Twilio call: {e}")
            errors.append(str(e))

    # Every configured carrier was tried and none accepted the call: report the failure
    # instead of falling through to simulation mode.
    if carrier_configured:
        release_active_call(formatted_phone)
        error = errors[0] if errors else "no carrier accepted the call"
        print(f"Telephony: Outbound call to {formatted_phone} FAILED: {error}")
        return {"ok": False, "provider": None, "error": error, "request_id": None}

    # 3. Standalone simulation / mock (only when no carrier credentials exist at all, e.g. local dev)
    print("Telephony (Simulation Mode): Dispatched outbound call signal.")
    print(f"Telephony (Simulation Mode): Route: {config.NGROK_URL}/telecmi/answer?direction=outbound&phone={formatted_phone}")
    return {"ok": True, "provider": "simulation", "error": None, "request_id": None}

