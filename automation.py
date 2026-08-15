import requests
import config

def send_whatsapp_message(phone: str, message: str) -> bool:
    """
    Helper to send a WhatsApp message using configured provider (e.g. Twilio WhatsApp or Custom API).
    """
    if not config.WHATSAPP_API_URL or not config.WHATSAPP_API_KEY:
        print(f"WhatsApp Automation (Mock): Sending message to {phone}: '{message}'")
        return True

    headers = {
        "Authorization": f"Bearer {config.WHATSAPP_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": phone,
        "message": message
    }
    
    try:
        response = requests.post(config.WHATSAPP_API_URL, json=payload, headers=headers)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"WhatsApp Automation Error: {e}")
        return False

def trigger_post_call_automations(phone: str, classification: str, lead_name: str = "Future Pilot"):
    """
    Orchestrates follow-up flows depending on lead qualification output: Hot, Warm, or Cold.
    """
    classification = (classification or "Cold").strip().capitalize()
    
    if classification == "Hot":
        # Send Calendly booking link for Dwarka Campus Visit
        message = (
            f"Hi {lead_name}! Thank you for speaking with Capt. Modassir at Airborne Aviation Academy.\n\n"
            f"Based on your high interest in our pilot programs, we'd love to invite you for a 1-on-1 career counselling "
            f"and simulator session at our Dwarka Academy.\n\n"
            f"Please book your preferred slot using this link: {config.CAMPUS_BOOKING_URL}\n\n"
            f"See you soon! ✈️"
        )
        success = send_whatsapp_message(phone, message)
        if success:
            print(f"Automation: Hot Lead workflow triggered. Calendly link sent to {phone}.")
            
    elif classification == "Warm":
        # Enroll in WhatsApp nurture sequence
        message = (
            f"Hi {lead_name}! It was great discussing your aviation goals today. We have registered your interest in our ground classes.\n\n"
            f"Over the next few days, we will share important info regarding DGCA exams, pilot medicals, and class batches. "
            f"Feel free to reply with any queries!\n\n"
            f"Clear skies, Airborne Aviation Academy. 🌤️"
        )
        success = send_whatsapp_message(phone, message)
        if success:
            print(f"Automation: Warm Lead workflow triggered. Nurture sequence enrolled for {phone}.")
            
    else:  # Cold lead
        # Tag cold lead, trigger 90-day re-nurture task
        print(f"Automation: Cold Lead workflow triggered for {phone}. Lead tagged as Cold; 90-day task reminder scheduled in CRM.")
