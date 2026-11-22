import requests
import json
import config

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

if not config.GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY is not set.")

# Persistent session for connection pooling and low latency
_gemini_session = requests.Session()

def chat_with_gemini(prompt: str, history: list = None, system_prompt: str = "", json_mode: bool = False) -> str:
    """
    Integrates with Google Gemini API via REST requests to process conversations.
    Uses persistent HTTP keep-alive connection and sub-second model routing.
    """
    preferred_model = config.GEMINI_MODEL or "gemini-3.8-flash"
    fallback_models = [preferred_model, "gemini-3.8-flash", "gemini-flash-latest"]
    # De-duplicate while preserving order
    models_to_try = list(dict.fromkeys(fallback_models))
    
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": config.GEMINI_API_KEY
    }
    
    # Translate history messages to Gemini format: role 'user' or 'model'
    contents = []
    if history:
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            # Ignore role = system since it's passed separately
            if msg["role"] in ["user", "assistant"]:
                contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
                
    # Add current prompt
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })
    
    generation_config = {
        "maxOutputTokens": 400 if json_mode else 120,
        "temperature": 0.2 if json_mode else 0.4
    }
    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    payload = {
        "contents": contents,
        "generationConfig": generation_config
    }
    
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }
        
    last_err = None
    for candidate_model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent"
        try:
            response = _gemini_session.post(url, json=payload, headers=headers, timeout=5)
            if response.status_code in [500, 503, 429]:
                print(f"Gemini {candidate_model} returned {response.status_code}. Trying next model...")
                continue
            response.raise_for_status()
            res_data = response.json()
            candidates = res_data.get('candidates', [])
            if candidates:
                parts = candidates[0].get('content', {}).get('parts', [])
                text = ''.join([p.get('text', '') for p in parts if 'text' in p])
                if text:
                    return text
        except Exception as e:
            last_err = e
            print(f"Gemini model {candidate_model} failed ({e}). Trying fallback...")

    if last_err:
        raise last_err

def chat_with_vertex_ai(prompt: str, history: list = None, system_prompt: str = "", json_mode: bool = False) -> str:
    """
    Direct Vertex AI GenAI SDK path running natively inside Google Cloud Run.
    Billed to Google Cloud project using default Application Credentials (ADC).
    """
    if not genai or not types:
        raise RuntimeError("google-genai SDK not available in environment.")
    
    genai_client = genai.Client(
        vertexai=True,
        project=getattr(config, "GCP_PROJECT", "airborne-aviation-505100"),
        location=getattr(config, "GCP_LOCATION", "asia-south1")
    )
    
    contents = []
    if history:
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            if msg["role"] in ["user", "assistant"]:
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )
    )
    
    config_params = types.GenerateContentConfig(
        system_instruction=system_prompt if system_prompt else None,
        temperature=0.2 if json_mode else 0.4,
        max_output_tokens=400 if json_mode else 120,
        response_mime_type="application/json" if json_mode else None
    )
    vertex_model = getattr(config, "GEMINI_MODEL", None) or "gemini-3.8-flash"
    resp = genai_client.models.generate_content(
        model=vertex_model,
        contents=contents,
        config=config_params
    )
    return resp.text

def chat_with_gpt(prompt: str, history: list = None, system_prompt: str = "", json_mode: bool = False) -> str:
    """
    Main LLM interface for the voice agent.
    1. Primary: Google Gemini Studio REST API
    2. Secondary: Google Cloud Vertex AI (Cloud Run ADC)
    3. Fallback: Context-aware offline simulation (for dev/testing)
    """
    # 1. Primary: Gemini Studio if API Key is configured
    if config.GEMINI_API_KEY:
        try:
            res = chat_with_gemini(prompt, history, system_prompt, json_mode=json_mode)
            if res:
                return res
        except Exception as e:
            print(f"Gemini Studio failed ({e}). Trying Vertex AI...")

    # 2. Secondary: Vertex AI via Google Cloud ADC
    try:
        return chat_with_vertex_ai(prompt, history, system_prompt, json_mode=json_mode)
    except Exception as e:
        print(f"Vertex AI query failed: {e}")

    # 3. Context-aware offline mock fallback (handles all conversation categories)
    if json_mode:
        return json.dumps({
            "course_interest": "DGCA CPL Ground Classes",
            "booking_intent": "Counselling Call",
            "budget_status": "Ready",
            "timeline_urgency": "Immediate",
            "classification": "Hot"
        })

    prompt_lower = prompt.lower() if prompt else ""

    if any(w in prompt_lower for w in ["visit", "campus", "saturday", "sunday", "come", "see", "tour", "simulator tour"]):
        return (
            "Absolutely! You are most welcome to visit our campus at Ramphal Chowk, Dwarka. "
            "We have sessions available on Saturday and Sunday mornings. What time works best for you? "
            "I will note it down and our team will confirm via WhatsApp."
        )
    elif any(w in prompt_lower for w in ["simulator", "a320", "fbs", "cockpit"]):
        return (
            "Our Airbus A320 Fixed-Base Simulator is right here at our Dwarka campus. "
            "Each simulator session costs Rs. 12,000. Would you like to book a walkthrough or a hands-on session?"
        )
    elif any(w in prompt_lower for w in ["time", "slot", "11 am", "morning", "afternoon", "evening", "3 pm", "schedule", "book"]):
        return (
            "Perfect! I have noted your preferred time. Our admissions team will send a confirmation "
            "along with the campus address and syllabus brochure directly to your WhatsApp. See you soon! Clear skies!"
        )
    elif any(w in prompt_lower for w in ["fee", "cost", "price", "fees", "kitna", "paisa"]):
        return (
            "Thank you for asking. Our DGCA CPL Ground Classes fee is Rs. 2,70,000, covering all 5 DGCA papers "
            "plus RTR prep. Classes are mentored directly by Captain Navrang Singh with a batch size of maximum 25 students."
        )
    elif any(w in prompt_lower for w in ["eligibility", "qualification", "12th", "nios", "maths", "physics", "age"]):
        return (
            "For CPL, you need 10+2 with Physics and Mathematics. NIOS is 100 percent accepted by DGCA. "
            "Minimum age is 17 to start ground school, and 18 for the license. Would you like to know about medicals too?"
        )
    elif any(w in prompt_lower for w in ["cabin crew", "air hostess", "flight attendant"]):
        return (
            "Our Cabin Crew training program fee is Rs. 59,000 and the duration is 1 to 2 months. "
            "Eligibility is 10+2 in any stream, age 18 to 27. Would you like to visit the campus to learn more?"
        )
    elif any(w in prompt_lower for w in ["thank", "bye", "goodbye", "exit", "shukriya"]):
        return (
            "Thank you for calling Airborne Aviation Academy! We will send all the details to your WhatsApp. "
            "Have a wonderful day ahead. Clear skies! [EXIT]"
        )

    # History-aware continuation
    if history and len(history) > 2:
        last_assistant_msg = ""
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                last_assistant_msg = msg.get("content", "")
                break
        if "2,70,000" in last_assistant_msg or "fee" in last_assistant_msg.lower():
            return (
                "That is great to hear! Would you like to schedule a campus visit at our Ramphal Chowk, Dwarka centre? "
                "You can see the A320 simulator and meet Captain Navrang Singh in person."
            )

    return (
        "Thank you for contacting Airborne Aviation Academy, Dwarka. Captain Navrang Singh and our admissions team are here to help guide your pilot training journey. Which program or questions can I assist you with today?"
    )

# Alias for standard naming
chat_with_llm = chat_with_gpt
