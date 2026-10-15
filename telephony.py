import requests
import config
import database
import supabase_client

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
            
    print(f"Telephony: Initiating outbound call to {lead_name or 'Candidate'} at {formatted_phone}...")
    
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
        or "edc5b96c-9e10-4b1f-b2b0-528da3c30978"
    )
    token = getattr(config, "AGENT_TOKEN", "") or config.TELECMI_TOKEN or ""

    if token and app_id:
        carrier_configured = True
        try:
            from piopiy.voice import RestClient
            client = RestClient(token=token)
            raw_caller = "".join(filter(str.isdigit, str(config.TELECMI_PHONE_NUMBER or "917943446755")))
            if len(raw_caller) == 10:
                caller_id = "91" + raw_caller
            else:
                caller_id = raw_caller or "917943446755"

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
            pipeline = [
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

            clean_variables = {
                k: str(v) for k, v in (dossier.to_dict() if dossier else {}).items() 
                if v and k not in ["created_at"]
            }

            print(f"Telephony: Dispatching Piopiy AI call (caller_id={caller_id}, to={telecmi_to}, agent_id={app_id})...")
            try:
                res = client.ai.call(
                    caller_id=caller_id,
                    to_number=telecmi_to,
                    agent_id=app_id,
                    variables=clean_variables
                )
                print(f"Telephony: PioPiy AI call dispatched with pre-call variables: {res}")
                body_err = _response_error(res)
                if body_err:
                    raise RuntimeError(body_err)
                return {"ok": True, "provider": "piopiy_ai", "error": None,
                        "request_id": res.get("request") if isinstance(res, dict) else None}
            except Exception as ai_err:
                print(f"Telephony: AI call failed ({ai_err}), attempting client.pcmo.call fallback...")
                try:
                    res = client.pcmo.call(
                        caller_id=caller_id,
                        to_number=telecmi_to,
                        app_id=app_id,
                        pipeline=pipeline
                    )
                    print(f"Telephony: PioPiy PCMO call dispatched: {res}")
                    body_err = _response_error(res)
                    if body_err:
                        raise RuntimeError(body_err)
                    return {"ok": True, "provider": "piopiy_pcmo", "error": None,
                            "request_id": res.get("request") if isinstance(res, dict) else None}
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
                from_num = int("".join(filter(str.isdigit, str(config.TELECMI_PHONE_NUMBER or "917943446755"))))
                to_num = int("".join(filter(str.isdigit, str(telecmi_to))))
            except Exception:
                from_num = config.TELECMI_PHONE_NUMBER or "917943446755"
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
        error = errors[0] if errors else "no carrier accepted the call"
        print(f"Telephony: Outbound call to {formatted_phone} FAILED: {error}")
        return {"ok": False, "provider": None, "error": error, "request_id": None}

    # 3. Standalone simulation / mock (only when no carrier credentials exist at all, e.g. local dev)
    print("Telephony (Simulation Mode): Dispatched outbound call signal.")
    print(f"Telephony (Simulation Mode): Route: {config.NGROK_URL}/telecmi/answer?direction=outbound&phone={formatted_phone}")
    return {"ok": True, "provider": "simulation", "error": None, "request_id": None}

