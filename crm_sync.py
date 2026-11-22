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
    fields = {
        "name": lead_data.get("name", "Future Pilot"),
        "phone": lead_data.get("phone"),
        "email": lead_data.get("email"),
        "Course": lead_data.get("course_interest"),
        "Classification": lead_data.get("classification"),
        "Status": lead_data.get("crm_status") or lead_data.get("status") or lead_data.get("classification"),
        "Budget Status": lead_data.get("budget_status"),
        "Timeline Urgency": lead_data.get("timeline_urgency")
    }

    if lead_data.get("lost_reason"):
        fields["Lost Reason"] = lead_data.get("lost_reason")
    if lead_data.get("counselor_name"):
        fields["Assigned Counselor"] = lead_data.get("counselor_name")
    if lead_data.get("followup_time"):
        fields["Followup Date"] = str(lead_data.get("followup_time"))
    if lead_data.get("meeting_time"):
        fields["Meeting Date"] = str(lead_data.get("meeting_time"))

    payload = {
        "fields": fields,
        "actions": []
    }

    # Add counselor assignment action if assigned
    if lead_data.get("counselor_name"):
        payload["actions"].append({
            "type": "ASSIGNMENT",
            "text": f"Assigned Counselor: {lead_data.get('counselor_name')}. Reason: {lead_data.get('counselor_reason', 'Automated qualification assignment')}"
        })

    # Add follow-up task action if scheduled
    if lead_data.get("followup_time"):
        payload["actions"].append({
            "type": "TASK",
            "text": f"Follow-up Call: {lead_data.get('followup_notes') or 'Follow-up with candidate'}",
            "due_date": str(lead_data.get("followup_time"))
        })

    # Add meeting action if scheduled
    if lead_data.get("meeting_time"):
        payload["actions"].append({
            "type": "MEETING",
            "text": f"Campus Visit & Simulator Session: {lead_data.get('meeting_notes') or 'Meeting at Dwarka campus'}",
            "due_date": str(lead_data.get("meeting_time"))
        })
    
    # Append transcript as a system note
    if transcript:
        payload["actions"].append({
            "type": "SYSTEM_NOTE",
            "text": f"AI Voice Advisor Call Log:\n\n{transcript}"
        })
        
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            print(f"CRM Sync: Lead {lead_data.get('phone')} successfully synced to TeleCRM.")
            return True
        else:
            print(f"CRM Sync Error: TeleCRM API returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"CRM Sync Connection Error: {e}")
        return False
