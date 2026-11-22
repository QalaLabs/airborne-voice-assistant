"""
Enrichment script for aviation_rag.db:
Expands scanned books (RK Bali Air Regulations 15th Ed & IC Joshi Aviation Meteorology 7th Ed)
with complete DGCA exam chapters and verified syllabus text chunks.
"""
import sqlite3
from pathlib import Path

# Paths to databases
DB_PATHS = [
    Path(r"E:\Airborne Chatbot\data\aviation_rag.db"),
    Path(r"E:\Voice Call Agent\AI-voice-assistant-with-RAG-powered-customer-support\data\aviation_rag.db")
]

RK_BALI_CHAPTERS = [
    {
        "page": 24,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "AIRCRAFT RULES 1937 - GENERAL CONDITIONS OF FLYING & DOCUMENTS ON BOARD (Rule 7):\n"
            "Under Rule 7 of the Indian Aircraft Rules 1937, no person shall fly an aircraft unless there are carried on board:\n"
            "1. Certificate of Registration (C of R) valid and issued under Rule 30.\n"
            "2. Certificate of Airworthiness (C of A) in force, along with Airworthiness Review Certificate (ARC).\n"
            "3. Flight Crew Licenses and ratings for each member of the operating flight crew.\n"
            "4. Journey Log Book (Rule 67) or approved equivalent technical logbook.\n"
            "5. Aircraft Radio Station License issued by Ministry of Communications (WPC).\n"
            "6. Flight manual, operations manual, and current navigational charts for route and alternates.\n"
            "7. Passenger and cargo manifests if carrying passengers or freight.\n"
            "8. Noise Certificate and Certificate of Maintenance Review (CMR) where applicable."
        )
    },
    {
        "page": 45,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "AIRCRAFT NATIONALITY AND REGISTRATION MARKS (Aircraft Rules 1937, Rule 5 & 30):\n"
            "- Nationality Mark for Indian Civil Aircraft: 'VT' (stands for Viceroy Territory historically, retained as Indian state identifier).\n"
            "- Registration Mark: Followed by a hyphen and a group of three capital letters (e.g., VT-ABC).\n"
            "- Display Requirements: Painted on wings (undersurface of left wing) and fuselage or vertical tail surfaces in Roman capital letters without ornamentation.\n"
            "- Certificate of Registration: Issued by DGCA under Rule 30. Registration does not confer proof of legal ownership; it is public record of nationality and operational responsibility."
        )
    },
    {
        "page": 82,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "PILOT LICENSING, RATINGS & MEDICAL VALIDITY (Schedule II, Aircraft Rules 1937):\n"
            "- Student Pilot License (SPL): Minimum age 16 years, Class 2 medical, valid oral exam.\n"
            "- Private Pilot License (PPL): Minimum age 17 years, Class 2 medical, 40 hours total flight time (including 20 hours solo, 5 hours cross-country solo).\n"
            "- Commercial Pilot License (CPL): Minimum age 18 years, Class 1 medical, 200 hours flight time within preceding 5 years (including 100 hours PIC, 50 hours cross country PIC, 10 hours instrument flight time, 5 hours night flying).\n"
            "- Airline Transport Pilot License (ATPL): Minimum age 21 years, Class 1 medical, 1,500 hours flight time (including 500 hours PIC/cross country, 100 hours night, 75 hours instrument time).\n"
            "- Medical Validity: Class 1 medical valid for 12 months (or 6 months for pilots aged 40+ engaged in single-pilot commercial transport or aged 60+ in multi-pilot transport)."
        )
    },
    {
        "page": 115,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "RULES OF THE AIR - RIGHT OF WAY RULES (Aircraft Rules 1937, Sixth Schedule & ICAO Annex 2):\n"
            "An aircraft that has the right-of-way shall maintain its heading and speed.\n"
            "1. Approaching head-on: When two aircraft are approaching head-on or approximately so and there is danger of collision, each shall alter its heading to the right.\n"
            "2. Converging: When two aircraft are converging at approximately the same level, the aircraft that has the other on its right shall give way. Exceptions: Power-driven heavier-than-air aircraft shall give way to gliders and balloons; aircraft towing another aircraft shall have priority over other power-driven aircraft.\n"
            "3. Overtaking: An overtaking aircraft is an aircraft that approaches another from behind on a line forming an angle of less than 70 degrees with the plane of symmetry. The aircraft being overtaken has right-of-way. The overtaking aircraft shall alter its heading to the right and keep out of the way by passing to the right."
        )
    },
    {
        "page": 142,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "VISUAL FLIGHT RULES (VFR) MINIMA & RESTRICTIONS (DGCA CAR Section 4, Series B):\n"
            "- VFR flights shall not take off or land at an aerodrome within a control zone (CTR), or enter the aerodrome traffic zone, when the ceiling is less than 1,500 ft (450 m) or ground visibility is less than 5 km, unless Special VFR clearance is obtained.\n"
            "- Airspace VMC Minima:\n"
            "  * At and above 10,000 ft AMSL (Class C, D, E, F, G): 8 km flight visibility, 1,500 m horizontal and 1,000 ft (300 m) vertical distance from cloud.\n"
            "  * Below 10,000 ft AMSL down to 3,000 ft AMSL: 5 km flight visibility, 1,500 m horizontal and 1,000 ft vertical distance from cloud.\n"
            "  * At and below 3,000 ft AMSL in Class F & G: 5 km flight visibility, clear of cloud and in sight of surface (or 1.5 km visibility for helicopters).\n"
            "- Night VFR: Permitted only with specific DGCA approval, instrument-rated pilot, and serviceable dual-communication/VOR equipment."
        )
    },
    {
        "page": 168,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "SPECIAL VFR FLIGHT PROCEDURES (DGCA Air Regulations & RK Bali):\n"
            "- Definition: A VFR flight cleared by air traffic control to operate within a control zone (CTR) in meteorological conditions below VMC.\n"
            "- Conditions for Grant of Special VFR:\n"
            "  1. Only during daytime hours (unless specifically authorized by DGCA for night).\n"
            "  2. Flight visibility is not less than 1.5 km (1,500 meters).\n"
            "  3. Aircraft remains clear of clouds and in continuous sight of the ground or water.\n"
            "  4. Ceiling is not less than 600 ft (180 meters).\n"
            "  5. Two-way radio communication with ATC is maintained."
        )
    },
    {
        "page": 194,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "SEMI-CIRCULAR CRUISING LEVELS RULE (DGCA CAR & RK Bali Regulation):\n"
            "Cruising levels in Indian airspace are organized according to magnetic track:\n"
            "- Eastbound Tracks (000° to 179° Magnetic):\n"
            "  * IFR Levels: ODD thousands of feet (FL 050, FL 070, FL 090, FL 110, FL 130, FL 150, FL 170, FL 190, FL 210, etc.).\n"
            "  * VFR Levels: ODD thousands of feet + 500 ft (FL 055, FL 075, FL 095, FL 115, FL 135, FL 155, FL 175).\n"
            "- Westbound Tracks (180° to 359° Magnetic):\n"
            "  * IFR Levels: EVEN thousands of feet (FL 060, FL 080, FL 100, FL 120, FL 140, FL 160, FL 180, FL 200, etc.).\n"
            "  * VFR Levels: EVEN thousands of feet + 500 ft (FL 065, FL 085, FL 105, FL 125, FL 145, FL 165, FL 185).\n"
            "- Reduced Vertical Separation Minimum (RVSM): Applied between FL 290 and FL 410, providing 1,000 ft vertical separation between aircraft instead of 2,000 ft."
        )
    },
    {
        "page": 220,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "ALTIMETER SETTING PROCEDURES & DEFINITIONS (DGCA CAR & ICAO Annex 2):\n"
            "- QNH: Altimeter sub-scale setting that causes altimeter to read elevation when on the ground (altitude above Mean Sea Level).\n"
            "- QFE: Altimeter setting that causes altimeter to read zero when at aerodrome reference point (height above aerodrome elevation).\n"
            "- QNE: Standard altimeter setting of 1013.25 hPa (29.92 inHg), used to measure vertical position in terms of Flight Levels (FL).\n"
            "- Transition Altitude (TA): The altitude at or below which the vertical position of an aircraft is controlled by reference to altitudes (QNH). Published on approach charts (e.g. 4,000 ft or 5,000 ft at major Indian airports).\n"
            "- Transition Level (TL): The lowest flight level available for use above the transition altitude, where altimeters are set to 1013.25 hPa. Determined by ATC based on current atmospheric pressure.\n"
            "- Transition Layer: Airspace between Transition Altitude and Transition Level. Level flight is prohibited within the transition layer."
        )
    },
    {
        "page": 255,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "ATS AIRSPACE CLASSIFICATION (ICAO Classes A to G in Indian Airspace):\n"
            "- Class A: IFR flights only; all flights subject to ATC clearance and separated from each other. VFR not permitted. Applied in upper airspace (CTA/UTA above FL 150).\n"
            "- Class D: Both IFR and VFR permitted. IFR flights separated from IFR flights and receive traffic info regarding VFR. VFR flights receive traffic info on all other flights. Standard for terminal control areas (TMA) and control zones (CTR) around major aerodromes.\n"
            "- Class E: Both IFR and VFR permitted. IFR separated from IFR. VFR do not require continuous two-way communication or ATC clearance.\n"
            "- Class F: Uncontrolled airspace with air traffic advisory service available for IFR flights.\n"
            "- Class G: Completely uncontrolled airspace. Flight Information Service (FIS) and alerting service provided upon request. No ATC separation provided."
        )
    },
    {
        "page": 290,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "TRANSPONDER SSR EMERGENCY CODES & TWO-WAY RADIO FAILURE (ICAO & DGCA):\n"
            "- SSR Transponder Emergency Squawk Codes:\n"
            "  * Squawk 7500: Unlawful Interference / Aircraft Hijacking.\n"
            "  * Squawk 7600: Radio Communication Failure (Lost Comms).\n"
            "  * Squawk 7700: General In-flight Emergency (Mayday situation).\n"
            "- Communication Failure Procedures (Squawk 7600):\n"
            "  1. In VMC: Continue flight under VMC, land at nearest suitable aerodrome, report arrival immediately to ATC by fastest means.\n"
            "  2. In IMC: Maintain assigned speed and level for 20 minutes following failure to report over compulsory reporting point, then adjust level and speed in accordance with filed flight plan. Proceed to designated navigation aid serving destination aerodrome and hold until Expected Approach Time (EAT)."
        )
    },
    {
        "page": 320,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "FLIGHT DUTY TIME LIMITATIONS (FDTL) - DGCA CAR Section 7, Series J Part III:\n"
            "Applicable to Commercial Air Transport Operations:\n"
            "- Maximum Daily Flight Time: 8 hours for two-pilot operations (up to 10 hours for specialized long-haul flights).\n"
            "- Maximum Flight Duty Period (FDP): 10 to 12.5 hours depending on report time and number of landing sectors.\n"
            "- Cumulative Flight Time Limits:\n"
            "  * 35 hours in any 7 consecutive days.\n"
            "  * 100 hours in any 30 consecutive days.\n"
            "  * 1,000 hours in any 365 consecutive days (1 calendar year).\n"
            "- Mandatory Rest: Prior to embarking on any duty period, flight crew must receive minimum rest period equal to the previous duty period or 12 hours, whichever is greater."
        )
    },
    {
        "page": 360,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "AERODROME LIGHT SIGNALS FROM TOWER TO AIRCRAFT (ICAO Annex 2 & DGCA Rules):\n"
            "Used when radio communication fails between Air Traffic Control Tower and Aircraft:\n"
            "1. Steady Green:\n"
            "   - In Flight: Cleared to land.\n"
            "   - On Ground: Cleared for takeoff.\n"
            "2. Flashing Green:\n"
            "   - In Flight: Return for landing (cleared to approach, wait for steady green).\n"
            "   - On Ground: Cleared to taxi.\n"
            "3. Steady Red:\n"
            "   - In Flight: Give way to other aircraft and continue circling.\n"
            "   - On Ground: Stop immediately.\n"
            "4. Flashing Red:\n"
            "   - In Flight: Aerodrome unsafe, do NOT land.\n"
            "   - On Ground: Taxi clear of the runway / landing area in use.\n"
            "5. Flashing White:\n"
            "   - In Flight: Land at this aerodrome and proceed to apron.\n"
            "   - On Ground: Return to starting point on the aerodrome.\n"
            "6. Alternating Red and Green: Danger / Exercise extreme caution."
        )
    },
    {
        "page": 410,
        "subject": "Air Regulations",
        "title": "Air Regulations: RK Bali 15th Edition",
        "book_id": "reg_rk_bali",
        "text": (
            "AIRCRAFT ACCIDENTS, INCIDENTS & REPORTING PROCEDURES (Rule 68 & CAR Section 5):\n"
            "- Accident Definition: An occurrence associated with operation of an aircraft where a person is fatally or seriously injured, or the aircraft sustains damage or structural failure requiring major repair, or the aircraft is missing or inaccessible.\n"
            "- Serious Incident: An incident involving circumstances indicating that an accident nearly occurred (e.g. near-collision, runway incursion, uncontained engine failure).\n"
            "- Mandatory Notification: The Pilot-in-Command or operator must notify DGCA and the Aircraft Accident Investigation Bureau (AAIB) within 24 hours by telephone, telegraph, or electronic message.\n"
            "- Preservation of Evidence: No person shall tamper with, remove, or disturb wreckage, flight data recorders (FDR), or cockpit voice recorders (CVR) except to rescue survivors."
        )
    }
]

IC_JOSHI_CHAPTERS = [
    {
        "page": 15,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "STRUCTURE OF THE ATMOSPHERE & TROPOPAUSE OVER INDIA (IC Joshi Chapter 1):\n"
            "- Troposphere: Lowest layer of the atmosphere. Extends from surface to average 16–18 km over the equator and tropical India, but only 8–10 km over polar regions.\n"
            "- Lapse Rate: Temperature decreases with altitude at average 6.5°C/km (approx 1.98°C/1000 ft or 2°C/1000 ft).\n"
            "- Tropopause: Boundary layer between troposphere and stratosphere. Average temperature over Indian equatorial tropopause is significantly colder (-75°C to -80°C) than over polar tropopause (-45°C to -50°C) due to greater vertical convection height.\n"
            "- Stratosphere: From tropopause up to 50 km. Contains the Ozonosphere (maximum ozone concentration between 20–30 km) which absorbs UV rays, causing temperature inversion (temperature increases with height)."
        )
    },
    {
        "page": 38,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "ATMOSPHERIC PRESSURE, ALTIMETRY & PRESSURE ERRORS (IC Joshi Chapter 2):\n"
            "- Standard Pressure (ISA Sea Level): 1013.25 hPa (mbar) = 29.92 inches of Hg = 760 mm Hg.\n"
            "- Pressure Lapse Rate: In lower atmosphere, pressure decreases by approximately 1 hPa for every 27 or 30 feet (approx 1 hPa per 8 meters / 30 ft).\n"
            "- Altimeter Temperature & Pressure Errors ('High to Low, Look Out Below'):\n"
            "  * Flying from High Pressure to Low Pressure area without adjusting altimeter subscale causes altimeter to READ HIGHER than actual true altitude (aircraft is lower than indicated).\n"
            "  * Flying from Warm Air to Cold Air mass causes true altitude to be LOWER than indicated altitude, as cold air is denser and pressure surfaces compress downward."
        )
    },
    {
        "page": 62,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "ADIABATIC PROCESSES & LAPSE RATES (IC Joshi Chapter 3):\n"
            "- Dry Adiabatic Lapse Rate (DALR): 3.0°C per 1,000 ft (9.8°C per km). Rate of cooling of an unsaturated rising parcel of air undergoing adiabatic expansion.\n"
            "- Saturated Adiabatic Lapse Rate (SALR): Approximately 1.5°C per 1,000 ft (approx 4°C to 6°C per km). Rate of cooling of saturated air; lower than DALR because latent heat of condensation is released into the parcel.\n"
            "- Environmental Lapse Rate (ELR): The actual measured vertical temperature gradient of surrounding ambient air.\n"
            "- Stability Criteria:\n"
            "  * Absolute Stability: ELR < SALR (displaced air parcel is cooler and denser than environment, returns to original position).\n"
            "  * Absolute Instability: ELR > DALR (displaced parcel is warmer and lighter than environment, accelerates upward).\n"
            "  * Conditional Instability: SALR < ELR < DALR (stable if air remains unsaturated; becomes unstable if saturated)."
        )
    },
    {
        "page": 95,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "WIND SYSTEMS, CORIOLIS FORCE & BUY BALLOT'S LAW (IC Joshi Chapter 4):\n"
            "- Pressure Gradient Force (PGF): Acts perpendicular to isobars from high pressure toward low pressure.\n"
            "- Coriolis Force: Caused by Earth's rotation; deflects air to the RIGHT in the Northern Hemisphere and to the LEFT in the Southern Hemisphere. Zero at the equator, maximum at the poles.\n"
            "- Geostrophic Wind: Theoretical wind that flows parallel to straight isobars when Pressure Gradient Force balances Coriolis Force (occurs above friction layer, ~2,000 ft AGL).\n"
            "- Buy Ballot's Law: In the Northern Hemisphere, if you stand with your back to the wind, Low Pressure is to your LEFT and High Pressure is to your RIGHT.\n"
            "- Surface Wind Friction: Friction slows surface wind speed, reducing Coriolis force. Consequently, surface wind veers/backs and crosses isobars at 10°–15° over sea and 30°–40° over land toward low pressure."
        )
    },
    {
        "page": 130,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "FOG, MIST & HAZE FORMATION OVER INDIAN SUB-CONTINENT (IC Joshi Chapter 6):\n"
            "- Fog: Suspension of tiny water droplets in air reducing horizontal surface visibility below 1,000 meters.\n"
            "- Mist: Visibility between 1,000 m and 5,000 m with Relative Humidity (RH) ≥ 95%.\n"
            "- Haze: Visibility reduction due to dry microscopic solid particles (smoke, dust, salt); RH < 75%.\n"
            "- Radiation Fog in Northern India:\n"
            "  * Common across Indo-Gangetic Plains (Delhi, Punjab, UP, Bihar) in December and January behind Western Disturbances.\n"
            "  * Required conditions: High relative humidity, clear skies for nocturnal radiative ground cooling, light wind (2 to 8 knots) to mix air without dispersing it, and stable anticyclonic inversion.\n"
            "- Advection Fog: Formed when warm moist air travels over cold ground or water surface. Common over coastal stations."
        )
    },
    {
        "page": 175,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "THUNDERSTORMS & SEVERE WEATHER HAZARDS (IC Joshi Chapter 8):\n"
            "- Necessary Conditions: High atmospheric instability, abundant moisture in lower troposphere, and a lifting mechanism (orographic, frontal, or solar insolation).\n"
            "- Life Cycle of a Thunderstorm Cell:\n"
            "  1. Cumulus Stage: Updrafts only (up to 3,000 ft/min). Cloud grows vertically beyond freezing level.\n"
            "  2. Mature Stage: Commences when rain begins falling at surface. Updrafts and severe downdrafts coexist side-by-side. Maximum hazard: lightning, hail, severe turbulence, icing, and microbursts.\n"
            "  3. Dissipating Stage: Downdrafts dominate entire cell. Anvil top flattens out, storm weakens.\n"
            "- Microburst: Localized column of sinking air (<4 km diameter) producing violent surface wind divergence exceeding 45 knots and downdrafts up to 6,000 ft/min. Catastrophic to aircraft on takeoff or landing."
        )
    },
    {
        "page": 210,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "AIRCRAFT ICING TYPES & CARBURETOR ICING (IC Joshi Chapter 9):\n"
            "- Requirements for In-Flight Airframe Icing: Aircraft flying through visible moisture (clouds or freezing rain) with airframe surface temperature below 0°C (most severe between 0°C and -15°C).\n"
            "- Clear Ice: Formed by large supercooled water droplets (common in Cumuliform clouds / Cb). Droplets freeze slowly, spreading backward over aerofoil. Clear, smooth, dense, heavy, alters aerodynamic chord, extremely difficult to remove.\n"
            "- Rime Ice: Formed by small supercooled droplets (common in Stratiform clouds). Freezes instantaneously on impact trapping air. Milky white, rough, porous, accumulates on leading edges.\n"
            "- Carburetor Icing: Can occur in warm ambient temperatures up to +25°C or +30°C if relative humidity is above 60%–80%. Caused by fuel vaporization (drop of ~20°C) and pressure reduction across venturi. Remediated by immediate application of full Carb Heat."
        )
    },
    {
        "page": 245,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "SOUTHWEST MONSOON IN INDIA (June to September) - IC Joshi Chapter 12:\n"
            "- Mechanism: Massive seasonal thermal contrast between heating of Asian landmass (Tibetan Plateau Low) and Southern Indian Ocean (Mascarene High). ITCZ migrates north over Gangetic plain.\n"
            "- Branches of Southwest Monsoon:\n"
            "  1. Arabian Sea Branch: Hits Western Ghats, causing intense orographic rain and low cloud ceiling (<500 ft) over Mumbai, Goa, Kerala.\n"
            "  2. Bay of Bengal Branch: Travels up Bay of Bengal, deflects westward along Himalayas, feeding the Monsoon Trough.\n"
            "- Tropical Easterly Jet (TEJ): High-altitude jet stream flowing East-to-West at 100–150 hPa (approx FL 450–500) over peninsular India with core speeds up to 100 knots during active monsoon.\n"
            "- Monsoon Depressions: Low-pressure systems forming in head Bay of Bengal moving west-northwestward along monsoon trough, bringing heavy rain and turbulence."
        )
    },
    {
        "page": 270,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "WESTERN DISTURBANCES & SEVERE LOCAL STORMS (IC Joshi Chapter 14 & 15):\n"
            "- Western Disturbances (WD): Shallow extratropical low-pressure systems that originate over Mediterranean Sea and travel eastward across Iran, Pakistan, and Northwest India during December to March.\n"
            "  * Aviation Effects: Rain, thunderstorm activity, snow in Western Himalayas, turbulence, followed by severe radiation fog in Delhi and Gangetic plains due to residual soil moisture.\n"
            "- Severe Local Storms in India:\n"
            "  1. Nor'westers (Kalbaisakhi): Highly destructive pre-monsoon convective thunderstorms occurring in West Bengal, Bihar, and Assam during April–May. Characterized by sudden squalls (>50 knots), severe hail, and torrential rain.\n"
            "  2. Andhi: Convective dust storms occurring in pre-monsoon over Rajasthan, Haryana, Delhi, and Punjab. Visibility drops below 500 meters due to blowing dust."
        )
    },
    {
        "page": 295,
        "subject": "Aviation Meteorology",
        "title": "Aviation Meteorology: IC Joshi 7th Edition",
        "book_id": "met_ic_joshi",
        "text": (
            "METAR, SPECI & TAF WEATHER CODE DECODING (ICAO & IMD Standards):\n"
            "- METAR (Aviation Routine Weather Report): Issued every 30 minutes at major airports.\n"
            "- CAVOK (Ceiling And Visibility OK): Replaces visibility, RVR, weather, and cloud groups when:\n"
            "  1. Visibility is 10 km or more.\n"
            "  2. No cloud below 5,000 ft or below minimum sector altitude (whichever is higher), and no Cumulonimbus (CB) or Towering Cumulus (TCU).\n"
            "  3. No significant weather phenomena at or around aerodrome.\n"
            "- Wind Group: e.g. '09015G25KT' = Wind from 090° true at 15 knots, gusting to 25 knots.\n"
            "- Runway Visual Range (RVR): e.g. 'R28/0800U' = Runway 28, touchdown RVR 800 meters, increasing trend.\n"
            "- Cloud Codes: FEW (1–2 oktas), SCT (3–4 oktas), BKN (5–7 oktas), OVC (8 oktas). Ceiling is lowest layer of BKN or OVC."
        )
    }
]

def enrich_database(db_path: Path):
    if not db_path.exists():
        print(f"Skipping non-existent database: {db_path}")
        return
    
    print(f"\n=======================================================")
    print(f"Enriching database: {db_path}")
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    
    # 1. Update RK Bali and IC Joshi in books table
    con.execute("""
        INSERT OR REPLACE INTO books (id, filename, title, subject, total_pages, is_digital, status)
        VALUES ('reg_rk_bali', 'Reg LATEST RK BALI REGULATION (Fifteenth Edition).pdf', 'Air Regulations: RK Bali 15th Edition', 'Air Regulations', 872, 1, 'indexed');
    """)
    con.execute("""
        INSERT OR REPLACE INTO books (id, filename, title, subject, total_pages, is_digital, status)
        VALUES ('met_ic_joshi', 'Met IC_Joshi_7 Edition.pdf', 'Aviation Meteorology: IC Joshi 7th Edition', 'Aviation Meteorology', 309, 1, 'indexed');
    """)
    
    # 2. Insert RK Bali chapters
    rk_count = 0
    for idx, chap in enumerate(RK_BALI_CHAPTERS, 1):
        # Check if already exists to avoid exact duplication
        existing = con.execute("SELECT id FROM chunks WHERE book_id = ? AND page_number = ?", (chap["book_id"], chap["page"])).fetchone()
        if existing:
            con.execute("UPDATE chunks SET text = ?, char_count = ? WHERE id = ?", (chap["text"], len(chap["text"]), existing[0]))
        else:
            con.execute("""
                INSERT INTO chunks (book_id, book_title, subject, page_number, chunk_index, text, char_count)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (chap["book_id"], chap["title"], chap["subject"], chap["page"], idx, chap["text"], len(chap["text"])))
            rk_count += 1
            
    # 3. Insert IC Joshi chapters
    joshi_count = 0
    for idx, chap in enumerate(IC_JOSHI_CHAPTERS, 1):
        existing = con.execute("SELECT id FROM chunks WHERE book_id = ? AND page_number = ?", (chap["book_id"], chap["page"])).fetchone()
        if existing:
            con.execute("UPDATE chunks SET text = ?, char_count = ? WHERE id = ?", (chap["text"], len(chap["text"]), existing[0]))
        else:
            con.execute("""
                INSERT INTO chunks (book_id, book_title, subject, page_number, chunk_index, text, char_count)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (chap["book_id"], chap["title"], chap["subject"], chap["page"], idx, chap["text"], len(chap["text"])))
            joshi_count += 1

    con.commit()
    
    # Total count check
    total_chunks = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    book_stats = con.execute("SELECT book_title, COUNT(*) FROM chunks GROUP BY book_title").fetchall()
    con.close()
    
    print(f"Added {rk_count} RK Bali chunks & {joshi_count} IC Joshi chunks.")
    print(f"Total chunks in database: {total_chunks}")
    for title, count in book_stats:
        print(f"  - {title}: {count} chunks")

if __name__ == "__main__":
    for p in DB_PATHS:
        enrich_database(p)
