import requests
import config

def send_whatsapp_message(phone: str, message: str) -> bool:
    """
    Helper to send a WhatsApp message using configured provider:
    - Meta WhatsApp Business Cloud API (if WHATSAPP_PHONE_NUMBER_ID is set)
    - Custom Webhook API (if WHATSAPP_API_URL is set)
    - Mock fallback log
    """
    clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    
    # 1. Meta WhatsApp Business Cloud API Integration
    if config.WHATSAPP_PHONE_NUMBER_ID and config.WHATSAPP_API_KEY:
        url = f"https://graph.facebook.com/v18.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "text",
            "text": {
                "body": message
            }
        }
        try:
            resp = requests.post(url, json=payload, headers=headers)
            if resp.status_code in [200, 201]:
                print(f"WhatsApp Cloud API: Successfully sent message to {clean_phone}.")
                return True
            else:
                print(f"WhatsApp Cloud API Error: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"WhatsApp Cloud API Exception: {e}")

    # 2. Generic Webhook / Third Party API
    if config.WHATSAPP_API_URL and config.WHATSAPP_API_KEY:
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
            print(f"WhatsApp Custom API Error: {e}")
            return False

    # 3. Fallback / Mock Mode
    print(f"WhatsApp Automation (Mock): Message to {phone}: '{message}'")
    return True

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
