import requests
import config

try:
    from twilio.rest import Client
except ImportError:
    Client = None

try:
    import piopiy
except ImportError:
    piopiy = None

def make_outbound_call(phone_number: str, lead_name: str) -> bool:
    """
    Triggers an outbound call using PioPiy / TeleCMI (primary) or Twilio (fallback).
    Bridges the call to the FastAPI '/telecmi/answer' or '/answer-call' endpoints.
    """
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
            
    print(f"Telephony: Initiating outbound call to {lead_name} at {formatted_phone}...")
    
    # 1. PioPiy Modern SDK (Primary)
    if config.TELECMI_TOKEN and piopiy:
        try:
            client = piopiy.RestClient(token=config.TELECMI_TOKEN)
            caller_id = config.TELECMI_PHONE_NUMBER or "917943446755"
            app_id = config.TELECMI_PIOPIY_APP_ID or config.TELECMI_APP_ID
            
            # Dynamic personalized greeting for the lead
            greeting_url = "https://storage.googleapis.com/airborne-aviation-media-prod/tts-audio/greeting_modassir.mp3"
            try:
                import database
                import assistant
                lead = database.get_lead_by_phone(formatted_phone)
                resolved_name = (lead.get("name") if lead else None) or lead_name or "Future Aviation Professional"
                course_interest = (lead.get("course_interest") if lead else None) or "Aviation Programs"
                source_str = ((lead.get("source") if lead else None) or "Facebook Ads").replace("_", " ").title()
                
                created_at = lead.get("created_at") if lead else None
                if created_at:
                    day = created_at.day
                    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
                    lead_date_str = f"{day}{suffix} {created_at.strftime('%B')}"
                else:
                    lead_date_str = "recently"

                if "cabin" in course_interest.lower():
                    greeting_text = f"Hi {resolved_name}, you filled a lead on {lead_date_str} on {source_str} showcasing your interest in our {course_interest}. I am Capt. Modassir from Airborne Aviation Academy Dwarka. How can I help you regarding your cabin crew training today?"
                else:
                    greeting_text = f"Hi {resolved_name}, you filled a lead on {lead_date_str} on {source_str} showcasing your interest in {course_interest}. I am Capt. Modassir from Airborne Aviation Academy Dwarka. How can I help you regarding your pilot training today?"

                print(f"Telephony: Synthesizing personalized greeting: '{greeting_text}'")
                greeting_url = assistant.get_greeting_voice_url(greeting_text)
                database.save_conversation_history(
                    formatted_phone,
                    [{"role": "assistant", "content": greeting_text}],
                    "outbound"
                )
            except Exception as ge:
                print(f"Telephony: Notice generating custom greeting ({ge}), using default.")

            builder = piopiy.PipelineBuilder()
            builder.play(greeting_url)
            builder.record()
            pipeline = builder.build()
            
            res = client.pcmo.call(
                caller_id=caller_id,
                to_number=telecmi_to,
                app_id=app_id,
                pipeline=pipeline
            )
            print(f"Telephony: PioPiy outbound call dispatched: {res}")
            return True
        except Exception as e:
            print(f"Telephony Error: PioPiy SDK dispatch error: {e}")

    # 1b. TeleCMI Legacy REST API fallback
    if config.TELECMI_APP_ID and config.TELECMI_APP_SECRET:
        try:
            answer_url = f"{config.NGROK_URL}/telecmi/answer?direction=outbound&phone={formatted_phone}"
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
                print(f"Telephony: TeleCMI call initiated successfully: {response.text}")
                return True
            else:
                print(f"Telephony: TeleCMI returned HTTP {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Telephony Error: TeleCMI dispatch error: {e}")

    # 2. Fallback to Twilio if configured
    if config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and Client:
        try:
            client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
            twiml_url = f"{config.NGROK_URL}/answer-call?direction=outbound&phone={formatted_phone}"
            
            call = client.calls.create(
                to=formatted_phone,
                from_=config.TWILIO_PHONE_NUMBER,
                url=twiml_url
            )
            print(f"Telephony: Twilio call created successfully. SID: {call.sid}")
            return True
        except Exception as e:
            print(f"Telephony Error: Failed to create Twilio call: {e}")
            return False

    # 3. Standalone simulation / mock
    print("Telephony (Simulation Mode): Dispatched outbound call signal.")
    print(f"Telephony (Simulation Mode): Route: {config.NGROK_URL}/telecmi/answer?direction=outbound&phone={formatted_phone}")
    return True

