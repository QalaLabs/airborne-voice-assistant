import config
from twilio.rest import Client

def make_outbound_call(phone_number: str, lead_name: str) -> bool:
    """
    Triggers an outbound call using the configured telephony API.
    Bridges the call to the FastAPI '/answer-call' or '/stream-call' endpoints.
    """
    # Normalize phone number (ensure country code)
    if not phone_number.startswith("+"):
        if len(phone_number) == 10:
            phone_number = "+91" + phone_number # Default to India country code
        else:
            phone_number = "+" + phone_number
            
    print(f"Telephony: Initiating outbound call to {lead_name} at {phone_number}...")
    
    # Check if Twilio API keys are configured
    if config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN:
        try:
            client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
            
            # The TwiML URL that tells Twilio how to handle the call once answered.
            # We redirect it to our FastAPI app's NGROK URL.
            twiml_url = f"{config.NGROK_URL}/answer-call?direction=outbound&phone={phone_number}"
            
            call = client.calls.create(
                to=phone_number,
                from_=config.TWILIO_PHONE_NUMBER,
                url=twiml_url
            )
            print(f"Telephony: Call created successfully. SID: {call.sid}")
            return True
        except Exception as e:
            print(f"Telephony Error: Failed to create Twilio call: {e}")
            return False
    else:
        # Standalone mock implementation when credentials are not present
        print("Telephony (Mock Mode): Twilio keys not configured. Simulating successful outbound SIP connection.")
        print(f"Telephony (Mock Mode): Routing call to webhook: {config.NGROK_URL}/answer-call?direction=outbound&phone={phone_number}")
        return True
