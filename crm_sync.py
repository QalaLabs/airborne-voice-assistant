import requests
import config

def sync_lead_with_telecrm(lead_data: dict, transcript: str = None) -> bool:
    """
    Syncs the qualified lead status, custom fields, and call notes/transcripts
    back to TeleCRM using the custom lead auto-update API.
    """
    if not config.TELECRM_API_KEY:
        print("CRM Sync (Mock): TeleCRM key not set. Skipping sync to TeleCRM dashboard.")
        print("CRM Sync (Mock) Lead Payload:", lead_data)
        return True

    url = f"https://app.telecrm.in/api/b1/enterprise/{config.TELECRM_API_KEY}/autoupdatelead"
    
    headers = {
        "Authorization": f"Bearer {config.TELECRM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Map fields to match TeleCRM custom schema exactly
    payload = {
        "fields": {
            "name": lead_data.get("name", "Future Pilot"),
            "phone": lead_data.get("phone"),
            "email": lead_data.get("email"),
            "Course": lead_data.get("course_interest"),
            "Classification": lead_data.get("classification"),
            "Budget Status": lead_data.get("budget_status"),
            "Timeline Urgency": lead_data.get("timeline_urgency")
        },
        "actions": []
    }
    
    # Append transcript as a system note
    if transcript:
        payload["actions"].append({
            "type": "SYSTEM_NOTE",
            "text": f"AI Voice Advisor Call Log:\n\n{transcript}"
        })
        
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            print(f"CRM Sync: Lead {lead_data.get('phone')} successfully synced to TeleCRM.")
            return True
        else:
            print(f"CRM Sync Error: TeleCRM API returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"CRM Sync Connection Error: {e}")
        return False
