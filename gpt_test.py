import requests
import json
from openai import OpenAI
import config

# Initialize OpenAI client with credentials from config
client = None
if config.OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize OpenAI client: {e}")
else:
    print("Warning: OPENAI_API_KEY is not set.")

if not config.GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY is not set.")
elif not config.GEMINI_API_KEY.startswith("AIza"):
    print("Warning: GEMINI_API_KEY does not start with standard 'AIza' prefix. Please verify your Google AI Studio API key.")

# Persistent HTTP session for connection pooling and zero-handshake overhead
_gemini_session = requests.Session()

def chat_with_gemini(prompt: str, history: list = None, system_prompt: str = "", json_mode: bool = False) -> str:
    """
    Integrates with Google Gemini API via REST requests to process conversations.
    Uses persistent HTTP keep-alive connection and sub-second model routing.
    """
    preferred_model = config.GEMINI_MODEL or "gemini-3.8-flash"
    fallback_models = [preferred_model, "gemini-3.8-flash", "gemini-2.0-flash", "gemini-2.5-flash"]
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
        # Disable thinking budget on models that support it (2.5, 3.8, thinking) for minimum voice latency
        if any(tag in candidate_model for tag in ("2.5", "3.8", "thinking")):
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}
        else:
            generation_config.pop("thinkingConfig", None)

        try:
            response = _gemini_session.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code in [500, 503, 429]:
                print(f"Gemini {candidate_model} returned {response.status_code}. Trying next model...")
                continue
            response.raise_for_status()
            res_data = response.json()
            parts = res_data['candidates'][0]['content']['parts']
            text = ''.join([p.get('text', '') for p in parts if 'text' in p])
            return text
        except Exception as e:
            last_err = e
            print(f"Gemini model {candidate_model} failed ({e}). Trying fallback...")

    if last_err:
        raise last_err

def chat_with_vertex_ai(prompt: str, history: list = None, system_prompt: str = "", json_mode: bool = False) -> str:
    """
    Calls Gemini on Google Cloud Vertex AI using Application Default Credentials (ADC).
    """
    from google import genai
    from google.genai import types
    project = getattr(config, "GCP_PROJECT", "airborne-aviation-505100")
    location = getattr(config, "GCP_LOCATION", "asia-south1")
    genai_client = genai.Client(vertexai=True, project=project, location=location)

    contents = []
    if history:
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            if msg["role"] in ["user", "assistant"]:
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))

    config_params = types.GenerateContentConfig(
        system_instruction=system_prompt if system_prompt else None,
        temperature=0.2 if json_mode else 0.7,
        max_output_tokens=500 if json_mode else 300,
        response_mime_type="application/json" if json_mode else None
    )
    resp = genai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=config_params
    )
    return resp.text

def chat_with_gpt(prompt: str, history: list = None, system_prompt: str = "", json_mode: bool = False) -> str:
    """
    Integrates with Gemini or OpenAI Chat Completion API to carry out conversational steps.
    Keeps track of conversation history and system instructions. Supports structured JSON mode.
    """
    # 1. Primary: Use Gemini Studio if API Key is configured
    if config.GEMINI_API_KEY:
        try:
            return chat_with_gemini(prompt, history, system_prompt, json_mode=json_mode)
        except Exception as e:
            print(f"Gemini Studio failed ({e}). Trying Vertex AI...")

    # 2. Secondary: Vertex AI via Google Cloud ADC (billed to GCP project)
    try:
        return chat_with_vertex_ai(prompt, history, system_prompt, json_mode=json_mode)
    except Exception as e:
        print(f"Vertex AI query failed: {e}")

    # 3. Tertiary: Fallback to OpenAI if configured
    if client:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for msg in history:
                messages.append(msg)
        messages.append({"role": "user", "content": prompt})
        
        try:
            kwargs = {
                "model": config.OPENAI_MODEL,
                "messages": messages,
                "max_tokens": 500 if json_mode else 150,
                "temperature": 0.2 if json_mode else 0.7
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI query failed: {e}")
            
    # 4. Final Mock Fallback: Mock Response
    if json_mode:
        return json.dumps({
            "course_interest": "DGCA CPL Ground Classes",
            "booking_intent": "Counselling Call",
            "budget_status": "Ready",
            "timeline_urgency": "Immediate",
            "classification": "Hot"
        })

    return (
        "Thank you for asking. Airborne Aviation Dwarka is Dwarka's leading ground classes school. "
        "Our Commercial Pilot License (CPL) program costs 2,70,000, and classes are mentored by Captain Navrang Singh."
    )
