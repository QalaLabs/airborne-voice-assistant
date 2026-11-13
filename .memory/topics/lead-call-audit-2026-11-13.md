# Lead Call Audit & Telephony Diagnosis (2026-11-13)

## Summary
Comprehensive audit of all lead calls, Cloud Run revision execution logs, and Cloud SQL (`airbornedb`) records for 2026-11-13.

## Call Outcomes Breakdown

### 1. Failed Outbound Calls (0s Duration - Never Reached PSTN)
- **Shyam Pandey** (`+919999797985`) — Cadet Pilot Preparation (09:40 AM IST)
- **Shyam kumar Soni** (`+917519535300`) — GD & PI Course (09:40 AM IST)
- **Palak Devi** (`+916387823024`) — Private Pilot License (12:45 PM IST)
**Root Cause**: TeleCMI dispatch request remained stuck in `call_queued` status for >35.0 seconds without initiating PSTN ringing. The automatic PCMO recovery fallback attempted direct dialing but returned `app_not_active`. Lead status updated to `FOLLOW_UP`.

### 2. Connected Outbound Calls (Early Disconnects / Brief Connections)
Candidates answered, WebRTC/SIP audio bridge connected, and opening personalized greeting by Piyush played, but candidates disconnected within 10–25s before qualification:
- **Akash Kumar Malik** (`+919368455450`) — ~15s (`EARLY_HANGUP`)
- **Viresh Dalal** (`+919837847003`) — ~15s (`EARLY_HANGUP`)
- **Akash Kumar** (`+918426902659`) — ~10s
- **Ritesh Kumar** (`+917303312243`) — ~10s (Later human follow-up: requested callback next week)
- **Ritik Sirsiya** (`+917496869965`) — ~12s (Later human follow-up: interested in Cabin Crew with sister)
- **Deepak Aggarwal** (`+917303017062`) — ~27s (Test lead)
- **RINKU SINGH** (`+917900829398`) — ~12s (Test lead; also initiated inbound callback)
- **Nazim bhat** (`+916006313384`) — ~13s
- **Ayush gupta** (`+917355387267`) — ~18s

### 3. Inbound Calls
- **+916005397751** (06:00 PM IST) — **2m 14s** active conversation session with the voice assistant.
- **+916006760151** (Aaashirwad, 06:34 PM IST) — ~15s test inbound call.

## Infrastructure & Telephony Notes
- **Cloud SQL Instance**: `airborne-aviation-505100:asia-south1:airborne-db`.
  - Primary Public IP: `34.100.212.80` (Authorized network `0.0.0.0/0`, user `airborne_app_user`, database `airbornedb`).
  - Cloud Run connects via unix domain socket: `/cloudsql/airborne-aviation-505100:asia-south1:airborne-db`.
- **Database Warning**: `record_call_outcome` encountered `violates foreign key constraint "voice_calls_lead_id_fkey"` on legacy table `voice_calls` because lead IDs reference `leads(id)` while legacy `voice_calls` referenced `voice_leads(id)`. Modern table `lead_activities` received all records properly.
