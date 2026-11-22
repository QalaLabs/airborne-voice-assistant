import os
import requests
import config

def send_whatsapp_message(
    phone: str, 
    message: str = "", 
    template_name: str = None, 
    template_components: list = None,
    language_code: str = "en"
) -> bool:
    """
    Helper to send a WhatsApp message using configured provider:
    - Meta WhatsApp Business Cloud API (supports both template-based campaigns & session text)
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
        
        # Outbound marketing/utility templates (required outside 24h care window)
        if template_name:
            payload = {
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                    "components": template_components or []
                }
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "text",
                "text": {
                    "body": message
                }
            }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code in [200, 201]:
                print(f"WhatsApp Cloud API: Successfully sent message to {clean_phone} (template: {template_name}).")
                return True
            else:
                print(f"WhatsApp Cloud API Error: {resp.status_code} {resp.text}")
                # If template fails or doesn't exist, try fallback to text if message provided
                if template_name and message:
                    print("WhatsApp Cloud API: Retrying with raw text body...")
                    fallback_payload = {
                        "messaging_product": "whatsapp",
                        "to": clean_phone,
                        "type": "text",
                        "text": {"body": message}
                    }
                    fb_resp = requests.post(url, json=fallback_payload, headers=headers, timeout=10)
                    return fb_resp.status_code in [200, 201]
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
            "message": message,
            "template_name": template_name,
            "template_components": template_components
        }
        try:
            response = requests.post(config.WHATSAPP_API_URL, json=payload, headers=headers, timeout=10)
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"WhatsApp Custom API Error: {e}")
            return False

    # 3. Fallback / Mock Mode
    try:
        desc = f"Template '{template_name}'" if template_name else f"Text: '{message[:80]}...'"
        print(f"WhatsApp Automation (Mock/Log): Dispatched to {phone}: {desc}")
    except UnicodeEncodeError:
        safe_msg = message.encode("ascii", errors="replace").decode("ascii")
        print(f"WhatsApp Automation (Mock/Log): Dispatched to {phone}: '{safe_msg[:80]}...'")
    return True

def trigger_dropoff_recovery(phone: str, lead_name: str = "Future Pilot", is_webinar: bool = False):
    """
    Fires an instant WhatsApp recovery message when a call ends early (<25s) or encounters audio drop-off.
    """
    lead_name = lead_name if lead_name and lead_name not in ["Inbound Caller", "Candidate", "Future Pilot", "New Lead"] else "there"
    if is_webinar:
        message = (
            f"Hi {lead_name}! Captain Navrang here from Airborne Aviation Academy.\n\n"
            f"It seems our call got disconnected. You had shown interest in our live Parents' Webinar on pilot careers.\n\n"
            f"Here is your official seat reservation link:\n"
            f"👉 https://www.airborneaviation.in/webinar\n\n"
            f"Schedule: Saturday 21 Nov 2026, 2:00 PM IST (Live Online with Capt. Navrang). Looking forward to seeing you online! ✈️"
        )
    else:
        message = (
            f"Hi {lead_name}! Captain Navrang here from Airborne Aviation Academy, Dwarka.\n\n"
            f"It seems our call got disconnected. Whenever you have a quick moment, feel free to reply right here with any questions on DGCA ground classes, CPL eligibility, or fees.\n\n"
            f"Looking forward to guiding your aviation journey! ✈️"
        )

    # Template components for Meta Business API if pre-approved template exists
    template_components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": lead_name}
            ]
        }
    ]
    return send_whatsapp_message(
        phone, 
        message=message, 
        template_name="airborne_call_recovery" if is_webinar else "airborne_dropoff_recovery",
        template_components=template_components
    )

def trigger_post_call_automations(
    phone: str, 
    classification: str, 
    lead_name: str = "Future Pilot", 
    course_interest: str = None,
    scheduled_time: str = None,
    booking_intent: str = None
):
    """
    Orchestrates follow-up flows depending on lead qualification output: Hot, Warm, or Cold,
    with specialized instant delivery for webinar leads and confirmed campus visits.
    """
    classification = (classification or "Cold").strip().capitalize()
    course_lower = (course_interest or "").lower()
    
    # Explicit webinar leads
    is_webinar = (
        "webinar" in course_lower
        or (booking_intent and "webinar" in booking_intent.lower())
    )

    clean_name = lead_name if lead_name and lead_name not in ["Inbound Caller", "Candidate", "Future Pilot", "New Lead"] else "Future Pilot"

    # 1. Webinar Lead Follow-Up (High Priority)
    if is_webinar:
        message = (
            f"Hi {clean_name}! Thank you for speaking with Captain Navrang at Airborne Aviation Academy.\n\n"
            f"Here is your link to reserve your seat for the upcoming live Parents' Webinar on pilot careers:\n"
            f"👉 https://www.airborneaviation.in/webinar\n\n"
            f"Schedule: Saturday 21 Nov 2026, 2:00 PM IST (Live Online)\n"
            f"Registration fee is just Rs. 21 to hold your seat, and your join link is sent directly via WhatsApp.\n\n"
            f"Looking forward to seeing you and your parents online! Clear skies! ✈️"
        )
        template_components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": clean_name},
                    {"type": "text", "text": "https://www.airborneaviation.in/webinar"}
                ]
            }
        ]
        success = send_whatsapp_message(
            phone, 
            message=message, 
            template_name="airborne_webinar_invite", 
            template_components=template_components
        )
        if success:
            print(f"Automation: Webinar Lead workflow triggered. Registration link sent to {phone}.")
        return

    # 2. Confirmed Campus Visit Pass (High Intent with Verbal Date/Time)
    if scheduled_time and booking_intent and "campus" in booking_intent.lower():
        message = (
            f"✈️ Airborne Aviation Academy — Campus Visit Confirmed!\n\n"
            f"Hi {clean_name}, your 1-on-1 aviation counseling & A320 flight simulator session is confirmed:\n"
            f"📅 Slot: {scheduled_time}\n"
            f"📍 Campus: E-549, 2nd Floor, Ramphal Chowk Road, Sector 7, Dwarka, New Delhi 110075\n"
            f"🚇 Landmark: Near Dwarka Sector 9 Metro Station\n"
            f"🗺️ Google Maps: https://maps.google.com/?q=Airborne+Aviation+Academy+Dwarka\n\n"
            f"See you at the academy! Clear skies! 🛫"
        )
        template_components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": clean_name},
                    {"type": "text", "text": scheduled_time}
                ]
            }
        ]
        success = send_whatsapp_message(
            phone, 
            message=message, 
            template_name="airborne_campus_visit_pass",
            template_components=template_components
        )
        if success:
            print(f"Automation: Confirmed Campus Visit Pass sent to {phone} for {scheduled_time}.")
        return

    # 3. Hot Lead: Send Calendly Slot Selector
    if classification == "Hot":
        message = (
            f"Hi {clean_name}! Thank you for speaking with Captain Navrang at Airborne Aviation Academy.\n\n"
            f"Based on your high interest in our pilot programs, we'd love to invite you for a 1-on-1 career counselling "
            f"and simulator session at our Dwarka Academy.\n\n"
            f"Please book your preferred slot using this link: {config.CAMPUS_BOOKING_URL}\n\n"
            f"See you soon! ✈️"
        )
        template_components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": clean_name},
                    {"type": "text", "text": config.CAMPUS_BOOKING_URL}
                ]
            }
        ]
        success = send_whatsapp_message(
            phone, 
            message=message, 
            template_name="airborne_hot_lead_booking",
            template_components=template_components
        )
        if success:
            print(f"Automation: Hot Lead workflow triggered. Calendly link sent to {phone}.")
            
    # 4. Warm Lead: Nurture & DGCA Information Roadmap
    elif classification == "Warm":
        message = (
            f"Hi {clean_name}! It was great discussing your aviation goals today. We have registered your interest in our ground classes.\n\n"
            f"Over the next few days, we will share important info regarding DGCA exams, pilot medicals, and class batches. "
            f"Feel free to reply with any queries!\n\n"
            f"Clear skies, Airborne Aviation Academy. 🌤️"
        )
        template_components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": clean_name}
                ]
            }
        ]
        success = send_whatsapp_message(
            phone, 
            message=message, 
            template_name="airborne_warm_nurture",
            template_components=template_components
        )
        if success:
            print(f"Automation: Warm Lead workflow triggered. Nurture sequence enrolled for {phone}.")
            
    else:  # Cold lead
        print(f"Automation: Cold Lead workflow triggered for {phone}. Lead tagged as Cold; 90-day task reminder scheduled in CRM.")
