#!/usr/bin/env python3
"""
Sentence-Level Legal Text Analysis for MPA Enforcement Readiness
================================================================

This script is the SOLE scoring methodology for both indices in the analysis:

  1. Regulation Preparedness Index (MPA-level, 0-100)
     Applied to 9,740 regulatory zonations from ProtectedSeas Navigator.

  2. Legislation Readiness Index (Country-level, 0-100)
     Applied to 119 FAOLEX fisheries legislation documents.

METHODOLOGY
-----------
We employ rule-based computational legal text analysis, a standard approach
in legal informatics for scoring regulatory and legislative documents. The
method operates at the sentence level rather than the document level:

  1. Text is segmented into sentences using legal-text-aware boundary rules.
  2. Each sentence is classified by legal function:
       - Prohibition: unconditional mandatory restriction ("is prohibited")
       - Conditional prohibition: restriction with exceptions ("prohibited unless")
       - Requirement: mandatory obligation ("shall carry", "must report")
       - Permission: explicitly allowed activity ("is permitted")
       - Discretionary: hedged/conditional language ("may", "where appropriate")
       - Informational: descriptive or procedural without legal force
  3. Sentence-level classification drives dimension scores:
       - Legal strength: ratio and quality of mandatory vs discretionary provisions
       - Prohibition quality: number and specificity of prohibition sentences
       - Specificity: concrete activities, gear types, measurements in text
       - Technology integration: monitoring tech mentioned in legal context
       - Reporting: recordkeeping/documentation requirements
       - Text quality: structural completeness of regulatory text
  4. Multilingual pattern matching supports EN/ES/FR/IT/ID texts.
  5. Negation-aware: "shall not fish" = prohibition, "may fish" = permission.

FRAMEWORK
---------
Grounded in the Environmental Law Institute (2016) "Legal Tools for
Strengthening Marine Protected Area Enforcement" handbook, which identifies
clear prohibition language, vessel identification, monitoring technology,
evidence documentation, and reporting mechanisms as essential elements of
enforceable MPA regulations.

REVISION HISTORY
----------------
  v1 (2026-04-01): version used for the submitted manuscript.
  v2 (2026-09-02): revision for npj Ocean Sustainability. Added "may not"
      (and Spanish/French/Italian equivalents) to the prohibition patterns;
      previously such sentences were classified as discretionary (219 of
      93,283 sentences, 152 zones). Effect on headline statistics is below
      the reporting precision (mean RPI 33.02 -> 33.11). Terminology:
      "regulatory zonation" is now "regulatory zone" in outputs and figures.

REPRODUCIBILITY
---------------
This script is fully deterministic. Given the same input data, it produces
identical scores on any machine with Python 3.8+ and pdfplumber. No
machine learning models, random seeds, or external APIs are used.

INPUT
-----
  - data/02_curated/input/navigator_priority_countries_202507.csv
  - data/03_external/legislation/texts/*.pdf + *_EN.txt

OUTPUT
------
  - outputs/latest/regulation_scores.csv              (9,740 MPA scores)
  - outputs/latest/legislation_scores.csv             (119 document scores)
  - outputs/latest/legislation_country_scores.csv     (15 country scores)
  - outputs/latest/manuscript_statistics.json          (key stats for manuscript)
  - outputs/latest/manuscript_legislation_statistics.json

REQUIREMENTS
------------
  Python 3.8+
  pip install pdfplumber  (for legislation PDF text extraction)

USAGE
-----
  python3 analysis/scripts/nlp_contextual_scoring.py
"""

import csv
import json
import math
import os
import re
import sys
import html
from collections import Counter, defaultdict

# ============================================================================
# CONFIGURATION
# ============================================================================

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH = os.path.join(ROOT_DIR, "data/02_curated/input/navigator_priority_countries_202507.csv")
TEXT_DIR = os.path.join(ROOT_DIR, "data/03_external/legislation/texts")
OUTPUT_DIR = os.path.join(ROOT_DIR, "outputs/latest")

COUNTRY_NAMES = {
    "AUS": "Australia", "CAN": "Canada", "CHL": "Chile", "ECU": "Ecuador",
    "GAB": "Gabon", "GRC": "Greece", "IDN": "Indonesia", "ITA": "Italy",
    "MYS": "Malaysia", "MEX": "Mexico", "NZL": "New Zealand", "PAN": "Panama",
    "MDV": "Republic of Maldives", "ZAF": "South Africa", "ESP": "Spain",
}

# ============================================================================
# LEGAL LANGUAGE PATTERNS (compiled regex for performance)
# ============================================================================
# Each pattern set is multilingual (EN/ES/FR/IT/ID) to handle the full
# FAOLEX corpus. Patterns use word boundaries and case-insensitive matching.

# --- Prohibition indicators ---
# These patterns identify unconditional mandatory restrictions.
PROHIBITION_PATTERNS = [
    re.compile(r'\b(?:is\s+)?(?:strictly\s+)?prohibited\b', re.I),
    re.compile(r'\b(?:is\s+)?forbidden\b', re.I),
    re.compile(r'\bshall\s+not\b', re.I),
    re.compile(r'\bmust\s+not\b', re.I),
    re.compile(r'\bnot\s+(?:be\s+)?permitted\b', re.I),
    re.compile(r'\bnot\s+(?:be\s+)?allowed\b', re.I),
    re.compile(r'\bis\s+(?:deemed\s+)?illegal\b', re.I),
    re.compile(r'\bunlawful(?:ly)?\b', re.I),
    re.compile(r'\bno\s+person\s+(?:shall|may|is)\b', re.I),
    # Revision (Sept 2026): "may not" is a prohibition in Commonwealth
    # drafting ("a vessel may not stop"); previously it fell through to the
    # discretionary pattern for "may". Multilingual equivalents added.
    re.compile(r'\bmay\s+not\b', re.I),
    re.compile(r'\bno\s+(?:se\s+)?podr[áa]n?\b', re.I),
    re.compile(r'\bne\s+(?:peut|peuvent)\s+(?:pas|plus)\b', re.I),
    re.compile(r'\bnon\s+(?:pu[òo]|possono)\b', re.I),
    re.compile(r'\bwithout\s+exception\b', re.I),
    re.compile(r'\bat\s+all\s+times\b', re.I),
    re.compile(r'\bbanned\b', re.I),
    # Spanish
    re.compile(r'\bprohibid[oa]\b', re.I),
    re.compile(r'\bqueda\s+prohibid[oa]\b', re.I),
    re.compile(r'\bse\s+prohibe\b', re.I),
    re.compile(r'\bno\s+(?:se\s+)?permit[eir]\b', re.I),
    # French
    re.compile(r'\binterdit[es]?\b', re.I),
    re.compile(r'\best\s+interdit\b', re.I),
    re.compile(r'\bil\s+est\s+interdit\b', re.I),
    # Italian
    re.compile(r'\bvietat[oia]\b', re.I),
    re.compile(r'\b[eè]\s+vietat[oia]\b', re.I),
    # Indonesian
    re.compile(r'\bdilarang\b', re.I),
]

# --- Requirement/obligation indicators ---
REQUIREMENT_PATTERNS = [
    re.compile(r'\bshall\b(?!\s+not)', re.I),
    re.compile(r'\bmust\b(?!\s+not)', re.I),
    re.compile(r'\brequired\s+to\b', re.I),
    re.compile(r'\bobligation\b', re.I),
    re.compile(r'\bmandatory\b', re.I),
    re.compile(r'\bis\s+required\b', re.I),
    re.compile(r'\bare\s+required\b', re.I),
    # Spanish
    re.compile(r'\bdeb(?:er[áa]|en)\b', re.I),
    re.compile(r'\bobligatori[oa]\b', re.I),
    # French
    re.compile(r'\bdoi(?:t|vent)\b', re.I),
    re.compile(r'\bobligatoire\b', re.I),
]

# --- Discretionary/permissive indicators ---
DISCRETIONARY_PATTERNS = [
    re.compile(r'\bmay\b(?!\s+not\b)', re.I),
    re.compile(r'\bshould\b', re.I),
    re.compile(r'\bcould\b', re.I),
    re.compile(r'\bmight\b', re.I),
    re.compile(r'\bat\s+(?:the\s+)?discretion\b', re.I),
    re.compile(r'\bwhere\s+(?:appropriate|practicable|possible)\b', re.I),
    re.compile(r'\bwhen\s+(?:appropriate|practicable|possible)\b', re.I),
    re.compile(r'\bif\s+(?:appropriate|practicable|possible|necessary)\b', re.I),
    re.compile(r'\bas\s+(?:appropriate|needed|necessary)\b', re.I),
    re.compile(r'\bunless\s+(?:authorized|otherwise)\b', re.I),
    re.compile(r'\bsubject\s+to\b', re.I),
    re.compile(r'\bwith\s+(?:the\s+)?(?:permission|authorization|approval)\b', re.I),
    # Spanish
    re.compile(r'\bpodr[áa]n?\b', re.I),
    re.compile(r'\bpuede[n]?\b', re.I),
    # French
    re.compile(r'\bpeut\b', re.I),
    re.compile(r'\bpeuvent\b', re.I),
]

# --- Exception/conditional weakening ---
EXCEPTION_PATTERN = re.compile(
    r'\b(?:unless|except|provided\s+that|notwithstanding|save\s+for|'
    r'other\s+than|salvo|excepto|a\s+menos\s+que|sauf|tranne)\b', re.I
)

# --- Technology/monitoring ---
TECHNOLOGY_PATTERNS = [
    re.compile(r'\b(?:VMS|vessel\s+monitoring\s+system)\b', re.I),
    re.compile(r'\b(?:AIS|automatic\s+identification\s+system)\b', re.I),
    re.compile(r'\bsatellite\b', re.I),
    re.compile(r'\bradar\b', re.I),
    re.compile(r'\belectronic\s+(?:monitor|surveillance|track)\w*\b', re.I),
    re.compile(r'\bremote\s+sens\w+\b', re.I),
    re.compile(r'\btransponder\b', re.I),
    re.compile(r'\btracking\s+(?:device|system|equipment)\b', re.I),
    re.compile(r'\bGPS\b'),
    re.compile(r'\bsurveillance\b', re.I),
    # Multilingual
    re.compile(r'\bsat[eé]lit\w*\b', re.I),
    re.compile(r'\bmonitoreo\b', re.I),
    re.compile(r'\brastreo\b', re.I),
    re.compile(r'\bsorveglianza\b', re.I),
    re.compile(r'\bpemantau\w*\b', re.I),
]

# --- Vessel/gear specificity ---
VESSEL_PATTERNS = [
    re.compile(r'\bvessel\b', re.I),
    re.compile(r'\bboat\b', re.I),
    re.compile(r'\bship\b', re.I),
    re.compile(r'\bcraft\b', re.I),
    re.compile(r'\btrawl\w*\b', re.I),
    re.compile(r'\bnet(?:s|ting)?\b', re.I),
    re.compile(r'\blongline\b', re.I),
    re.compile(r'\bgillnet\b', re.I),
    re.compile(r'\bseine\b', re.I),
    re.compile(r'\btrap\w*\b', re.I),
    re.compile(r'\bdredge\w*\b', re.I),
    re.compile(r'\bspear\b', re.I),
    re.compile(r'\bhook\b', re.I),
    # Multilingual
    re.compile(r'\bembarcaci[oó]n\b', re.I),
    re.compile(r'\bbuque\b', re.I),
    re.compile(r'\bnavire\b', re.I),
    re.compile(r'\bnave\b', re.I),
    re.compile(r'\bkapal\b', re.I),
]

# --- Reporting/recordkeeping ---
REPORTING_PATTERNS = [
    re.compile(r'\blogbook\b', re.I),
    re.compile(r'\blog\s+book\b', re.I),
    re.compile(r'\bcatch\s+(?:report|record|documentation)\b', re.I),
    re.compile(r'\b(?:shall|must|required\s+to)\s+report\b', re.I),
    re.compile(r'\breporting\s+requirement\b', re.I),
    re.compile(r'\brecord\s*keeping\b', re.I),
    re.compile(r'\blanding\s+declaration\b', re.I),
    re.compile(r'\bobserver\b', re.I),
    re.compile(r'\bharvest\s+report\b', re.I),
    re.compile(r'\binspection\s+report\b', re.I),
]

# --- Evidence/prosecution (legislation) ---
EVIDENCE_PATTERNS = [
    re.compile(r'\b(?:admissib|inadmissib)\w+\b', re.I),
    re.compile(r'\bevidence\b', re.I),
    re.compile(r'\bprima\s+facie\b', re.I),
    re.compile(r'\bpresumption\b', re.I),
    re.compile(r'\bcertificat\w+\b', re.I),
    re.compile(r'\belectronic\s+(?:evidence|record|data)\b', re.I),
    re.compile(r'\bsatellite\s+(?:evidence|data|record)\b', re.I),
    # Multilingual
    re.compile(r'\bprueba\b', re.I),
    re.compile(r'\bevidencia\b', re.I),
    re.compile(r'\bpreuve\b', re.I),
    re.compile(r'\bprova\b', re.I),
    re.compile(r'\bbukti\b', re.I),
    re.compile(r'\bpresunci[oó]n\b', re.I),
]

PENALTY_PATTERNS = [
    re.compile(r'\bfine[sd]?\b', re.I),
    re.compile(r'\bpenalt(?:y|ies)\b', re.I),
    re.compile(r'\bimprisonment\b', re.I),
    re.compile(r'\bforfeit\w+\b', re.I),
    re.compile(r'\bseiz\w+\b', re.I),
    re.compile(r'\bconfiscat\w+\b', re.I),
    re.compile(r'\bsanction\w*\b', re.I),
    re.compile(r'\boffence\b', re.I),
    re.compile(r'\boffense\b', re.I),
    re.compile(r'\bviolation\b', re.I),
    re.compile(r'\b\$\s*\d+', re.I),
    re.compile(r'\d+\s*(?:years?|months?)\s*(?:imprisonment|jail|prison)', re.I),
    # Multilingual
    re.compile(r'\bmulta\b', re.I),
    re.compile(r'\bsanci[oó]n\b', re.I),
    re.compile(r'\bprisi[oó]n\b', re.I),
    re.compile(r'\bamende\b', re.I),
    re.compile(r'\bemprisonnement\b', re.I),
    re.compile(r'\bammenda\b', re.I),
    re.compile(r'\breclusione\b', re.I),
    re.compile(r'\bdenda\b', re.I),
    re.compile(r'\bpidana\b', re.I),
    re.compile(r'\bpenjara\b', re.I),
]

ENFORCEMENT_AUTHORITY_PATTERNS = [
    re.compile(r'\b(?:enforce|enforcement)\b', re.I),
    re.compile(r'\bauthori[sz]ed\s+officer\b', re.I),
    re.compile(r'\binspect\w+\b', re.I),
    re.compile(r'\bboard\w*\b.*\bvessel\b', re.I),
    re.compile(r'\bvessel\b.*\bboard\w*\b', re.I),
    re.compile(r'\barrest\b', re.I),
    re.compile(r'\bdetain\b', re.I),
    re.compile(r'\bcoast\s+guard\b', re.I),
    re.compile(r'\bfisheries\s+officer\b', re.I),
    re.compile(r'\bprosecuti\w+\b', re.I),
    # Multilingual
    re.compile(r'\bfiscaliz\w+\b', re.I),
    re.compile(r'\binspecci[oó]n\b', re.I),
    re.compile(r'\bautoridad\w*\b', re.I),
    re.compile(r'\bcontr[oô]le\b', re.I),
    re.compile(r'\bgarde-c[oô]te\b', re.I),
    re.compile(r'\bispezion\w+\b', re.I),
    re.compile(r'\bguardia\b', re.I),
    re.compile(r'\bpengawas\w*\b', re.I),
    re.compile(r'\bpenegak\w*\b', re.I),
]

LIABILITY_PATTERNS = [
    re.compile(r'\bliab(?:le|ility)\b', re.I),
    re.compile(r'\bowner\b', re.I),
    re.compile(r'\boperator\b', re.I),
    re.compile(r'\bmaster\b', re.I),
    re.compile(r'\bresponsib(?:le|ility)\b', re.I),
    re.compile(r'\bjoint(?:ly)?\s+(?:and\s+severally\s+)?liable\b', re.I),
    re.compile(r'\bstrict\s+liability\b', re.I),
    re.compile(r'\bvicarious\b', re.I),
    # Multilingual
    re.compile(r'\bresponsab\w+\b', re.I),
    re.compile(r'\bpropietario\b', re.I),
    re.compile(r'\barmador\b', re.I),
    re.compile(r'\bcapit[aá]n\b', re.I),
    re.compile(r'\bpropri[eé]taire\b', re.I),
    re.compile(r'\barmatore\b', re.I),
    re.compile(r'\bpemilik\b', re.I),
    re.compile(r'\bnakhoda\b', re.I),
]

# --- Fisheries relevance (multilingual) ---
FISHERIES_PATTERN = re.compile(
    r'\b(?:fish\w*|marine|vessel|catch|harvest|trawl|aquaculture|'
    r'pelagic|coastal|ocean|maritime|sea|port|landing|quota|'
    r'pesca|pesquer[oa]|embarcaci[oó]n|buque|mar[ií]tim[oa]|'
    r'captura|desembarque|cuota|litoral|'
    r'p[eê]che|navire|halieutique|marin|'
    r'peschereccio|nave|marittim[oa]|'
    r'perikanan|ikan|kapal|laut|perairan|tangkap)\b', re.I
)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def clean_html(text):
    """Remove HTML tags and decode entities."""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def segment_sentences(text):
    """
    Split text into sentences using legal-text-aware boundary rules.

    Handles numbered lists (common in regulations), abbreviation dots,
    and HTML line breaks. Sentences shorter than 10 characters are
    discarded as fragments.
    """
    if not text or len(text.strip()) < 5:
        return []

    # Numbered lists: "1. Fishing is prohibited. 2. Mining is forbidden."
    text = re.sub(r'(\d+)\.\s+', r'\1) ', text)

    # Protect abbreviation dots
    text = re.sub(r'\b(No|Mr|Mrs|Dr|Prof|Inc|Ltd|Corp|Art|Sec|Ch|Vol)\.\s',
                  r'\1_DOT_ ', text)
    text = re.sub(r'\b([A-Z])\.\s', r'\1_DOT_ ', text)

    sentences = re.split(r'(?<=[.!?;])\s+(?=[A-Z0-9(])', text)
    sentences = [s.replace('_DOT_', '.') for s in sentences]

    # Also split on line breaks
    expanded = []
    for s in sentences:
        parts = re.split(r'<br\s*/?>|\n', s)
        expanded.extend(p.strip() for p in parts if p.strip())

    return [s for s in expanded if len(s) > 10]


def count_pattern_matches(text, patterns):
    """Count how many patterns match in text (unique pattern matches)."""
    if not text:
        return 0
    return sum(1 for p in patterns if p.search(text))


def classify_sentence(sentence):
    """
    Classify a sentence by legal function and assign a strength weight.

    Returns:
        (category, strength) where category is one of:
          'prohibition', 'conditional_prohibition', 'requirement',
          'permission', 'discretionary', 'informational'
        and strength is a float from 0.0 to 1.0.
    """
    s = sentence.strip()
    if len(s) < 10:
        return ('informational', 0.0)

    n_prohib = count_pattern_matches(s, PROHIBITION_PATTERNS)
    n_req = count_pattern_matches(s, REQUIREMENT_PATTERNS)
    n_disc = count_pattern_matches(s, DISCRETIONARY_PATTERNS)
    has_exception = bool(EXCEPTION_PATTERN.search(s))

    if n_prohib > 0:
        if has_exception:
            return ('conditional_prohibition', 0.6)
        return ('prohibition', 1.0)

    if n_req > 0 and n_disc == 0:
        if has_exception:
            return ('requirement', 0.6)
        return ('requirement', 0.8)

    if n_disc > 0:
        return ('discretionary', 0.2)

    if re.search(r'\b(?:is|are)\s+(?:allowed|permitted|authorized)\b', s, re.I):
        return ('permission', 0.3)

    return ('informational', 0.1)


# ============================================================================
# INDEX 1: REGULATION PREPAREDNESS SCORING (MPA-level, 0-100)
# ============================================================================

def score_regulation(restrictions, allowed, definitions, report_violations):
    """
    Score an MPA regulation on satellite-enforcement preparedness.

    The score is the sum of six additive components (0-100 total):
      1. Legal strength (0-35): sentence-level ratio of mandatory provisions
      2. Prohibition quality (0-20): number and specificity of prohibitions
      3. Specificity (0-15): concrete activities, gear, measurements
      4. Technology integration (0-10): monitoring tech in legal context
      5. Reporting/documentation (0-10): recordkeeping requirements
      6. Text quality (0-10): structural completeness

    Returns dict with total score and all component scores.
    """
    all_text = clean_html(" ".join(filter(None, [
        str(restrictions or ""), str(allowed or ""),
        str(definitions or ""), str(report_violations or "")
    ])))

    if len(all_text.strip()) < 20:
        return _empty_regulation_score()

    sentences = segment_sentences(all_text)
    if not sentences:
        sentences = [all_text]

    # Classify every sentence
    classifications = [classify_sentence(s) for s in sentences]
    categories = Counter(cat for cat, _ in classifications)
    strengths = [strength for _, strength in classifications]

    n_prohib = categories.get('prohibition', 0) + \
               categories.get('conditional_prohibition', 0)
    n_req = categories.get('requirement', 0)
    n_disc = categories.get('discretionary', 0)
    n_perm = categories.get('permission', 0)
    n_info = categories.get('informational', 0)

    # ---- Component 1: Legal Strength (0-35) ----
    # Based on proportion and quality of mandatory provisions
    mean_strength = sum(strengths) / len(strengths) if strengths else 0
    strong_count = n_prohib + n_req
    total_classified = strong_count + n_disc + n_perm + n_info
    strength_ratio = strong_count / total_classified if total_classified > 0 else 0
    legal_strength = (mean_strength * 0.5 + strength_ratio * 0.5) * 35

    # ---- Component 2: Prohibition Quality (0-20) ----
    if n_prohib > 0:
        prohib_score = 10  # base for having any prohibition
        if n_prohib >= 3:
            prohib_score += 5  # comprehensive coverage
        if n_prohib >= 5:
            prohib_score += 3  # extensive coverage
        # Bonus: specific prohibitions (name activities/gear)
        prohib_text = " ".join(
            s for s, (cat, _) in zip(sentences, classifications)
            if cat in ('prohibition', 'conditional_prohibition')
        )
        if count_pattern_matches(prohib_text, VESSEL_PATTERNS) >= 2:
            prohib_score += 2
        prohib_score = min(prohib_score, 20)
    else:
        prohib_score = 0

    # ---- Component 3: Specificity (0-15) ----
    specificity = 0
    text_lower = all_text.lower()

    activities = set(re.findall(
        r'\b(fishing|anchoring|trawling|dredging|mining|drilling|aquaculture|'
        r'harvesting|diving|mooring|extraction|discharge)\b', text_lower
    ))
    specificity += min(len(activities), 5) * 1.5  # up to 7.5

    gear = set(re.findall(
        r'\b(trawl\w*|net\w*|longline|gillnet|seine|trap|pot|dredge|'
        r'spear|hook|line|vessel|boat|ship|craft)\b', text_lower
    ))
    specificity += min(len(gear), 4) * 1.0  # up to 4

    numerics = re.findall(
        r'\d+\s*(?:meter|metre|feet|foot|nm|nautical|kg|kilogram|ton|'
        r'pound|inch|cm|mm|acre|hectare|km|mile)', text_lower
    )
    specificity += min(len(numerics), 3) * 1.0  # up to 3

    specificity = min(specificity, 15)

    # ---- Component 4: Technology Integration (0-10) ----
    tech_matches = count_pattern_matches(all_text, TECHNOLOGY_PATTERNS)
    if tech_matches >= 3:
        tech_score = 10
    elif tech_matches == 2:
        tech_score = 8
    elif tech_matches == 1:
        tech_score = 5
    else:
        tech_score = 0

    # ---- Component 5: Reporting/Documentation (0-10) ----
    report_matches = count_pattern_matches(all_text, REPORTING_PATTERNS)
    if report_matches >= 3:
        report_score = 10
    elif report_matches == 2:
        report_score = 7
    elif report_matches == 1:
        report_score = 4
    else:
        report_score = 0

    # ---- Component 6: Text Quality (0-10) ----
    text_quality = 0
    if len(all_text) >= 50:
        text_quality += 2
    if len(sentences) >= 3:
        text_quality += 2
    if n_prohib + n_req >= 1:
        text_quality += 3
    if re.search(r'\b(?:evidence|document|record|report|proof)\b', text_lower):
        text_quality += 1
    if re.search(r'\b(?:year-round|at all times|always|permanent|season|period)\b',
                 text_lower):
        text_quality += 2
    text_quality = min(text_quality, 10)

    # ---- Total ----
    total = min(100, legal_strength + prohib_score + specificity +
                tech_score + report_score + text_quality)

    # ---- Detect applicable improvements ----
    has_prohibition = n_prohib > 0
    has_vessel = bool(re.search(
        r'\b(?:vessel|boat|ship|craft|operator)\b', text_lower))
    has_vessel_id = bool(re.search(
        r'\b(?:identif|ais|vms|transponder|tracking|marking)\b', text_lower))
    has_monitoring = tech_matches > 0
    has_evidence = bool(re.search(
        r'\b(?:evidence|document|record|report|log|proof)\b', text_lower))
    has_temporal = bool(re.search(
        r'\b(?:year-round|at all times|always|permanent|season|period)\b', text_lower))
    has_reporting = report_matches > 0
    has_discretion = n_disc > 0

    applicable_fixes = []
    improvement = 0
    if not has_prohibition:
        applicable_fixes.append("clear_prohibition")
        improvement += 20
    if has_discretion:
        applicable_fixes.append("remove_discretion")
        improvement += 15
    if has_vessel and not has_vessel_id:
        applicable_fixes.append("vessel_id")
        improvement += 10
    if not has_monitoring:
        applicable_fixes.append("monitoring_reference")
        improvement += 10
    if not has_reporting:
        applicable_fixes.append("reporting_requirement")
        improvement += 10
    has_activity = bool(re.search(
        r'\b(?:fish|anchor|vessel|extract|discharge)\b', text_lower))
    if has_activity and not has_temporal:
        applicable_fixes.append("temporal_scope")
        improvement += 5
    if not has_evidence:
        applicable_fixes.append("evidence_pathway")
        improvement += 5

    improved_score = min(100, total + improvement)

    return {
        'preparedness_score': round(total, 1),
        'legal_strength': round(legal_strength, 1),
        'prohibition_score': prohib_score,
        'specificity_score': round(specificity, 1),
        'technology_score': tech_score,
        'reporting_score': report_score,
        'text_quality': text_quality,
        'n_sentences': len(sentences),
        'n_prohibitions': n_prohib,
        'n_requirements': n_req,
        'n_discretionary': n_disc,
        'has_prohibition': has_prohibition,
        'has_vessel_reference': has_vessel,
        'has_monitoring_reference': has_monitoring,
        'has_evidence_pathway': has_evidence,
        'has_reporting_requirement': has_reporting,
        'applicable_fixes': ",".join(applicable_fixes),
        'max_improvement': improvement,
        'improved_score': improved_score,
        'text_length': len(all_text),
    }


def _empty_regulation_score():
    return {
        'preparedness_score': 0, 'legal_strength': 0, 'prohibition_score': 0,
        'specificity_score': 0, 'technology_score': 0, 'reporting_score': 0,
        'text_quality': 0, 'n_sentences': 0, 'n_prohibitions': 0,
        'n_requirements': 0, 'n_discretionary': 0,
        'has_prohibition': False, 'has_vessel_reference': False,
        'has_monitoring_reference': False, 'has_evidence_pathway': False,
        'has_reporting_requirement': False,
        'applicable_fixes': "clear_prohibition,remove_discretion,vessel_id,"
                           "monitoring_reference,reporting_requirement,"
                           "temporal_scope,evidence_pathway",
        'max_improvement': 75, 'improved_score': 75, 'text_length': 0,
    }


# ============================================================================
# INDEX 2: LEGISLATION READINESS SCORING (Document-level, 0-100)
# ============================================================================

def extract_text_from_pdf(filepath):
    """Extract full text from a PDF using pdfplumber (no truncation)."""
    try:
        import pdfplumber
    except ImportError:
        print("  ERROR: pdfplumber not installed. Run: pip install pdfplumber")
        return ""
    try:
        parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    parts.append(page_text)
        return "\n".join(parts)
    except Exception:
        return ""


def score_legislation(text, year_hint=None):
    """
    Score a legislation document on five prosecution-readiness dimensions.

    Dimensions (summing to 0-100):
      1. Evidence admissibility (0-22)
      2. Penalty framework (0-22)
      3. Enforcement authority (0-17)
      4. Technology provisions (0-22)
      5. Liability framework (0-17)

    Legislative currency (recency of amendment) is excluded because it
    does not correlate with substantive readiness and would introduce
    circularity with temporal analyses.
    """
    if not text or len(text.strip()) < 50:
        return {
            'evidence_score': 0, 'penalty_score': 0, 'enforcement_score': 0,
            'technology_score': 0, 'liability_score': 0,
            'total_score': 0, 'n_sentences': 0, 'is_fisheries': False,
        }

    sentences = segment_sentences(text)
    if not sentences:
        sentences = [text]

    sent_classes = [classify_sentence(s) for s in sentences]

    # Fisheries relevance
    fisheries_hits = len(FISHERIES_PATTERN.findall(text))
    is_fisheries = fisheries_hits >= 5

    # ---- 1. Evidence Admissibility (0-22) ----
    ev_score = 0
    ev_hits = count_pattern_matches(text, EVIDENCE_PATTERNS)
    tech_evidence = bool(re.search(
        r'(?:satellite|electronic|VMS|AIS|digital|remote|'
        r'sat[eé]lit\w*|electr[oó]nic\w*|elettronic\w*)'
        r'\s+\w*\s*(?:evidence|record|data|proof|prueba|preuve|prova|bukti)',
        text, re.I
    ))
    if ev_hits >= 4: ev_score = 15
    elif ev_hits >= 2: ev_score = 11
    elif ev_hits >= 1: ev_score = 7
    if tech_evidence:
        ev_score = min(22, ev_score + 7)
    # Bonus: evidence in mandatory sentence context
    for s, (cat, _) in zip(sentences, sent_classes):
        if cat in ('prohibition', 'requirement') and re.search(
            r'\b(?:evidence|prueba|preuve|prova|bukti)\b', s, re.I
        ):
            ev_score = min(22, ev_score + 2)
            break

    # ---- 2. Penalty Framework (0-22) ----
    pen_score = 0
    pen_hits = count_pattern_matches(text, PENALTY_PATTERNS)
    has_amounts = bool(re.search(
        r'\$\s*[\d,]+|\d+\s*(?:dollars?|euros?|pesos?|rupiah|ringgit|rand)',
        text, re.I))
    has_imprison = bool(re.search(
        r'\b(?:imprison|jail|prison|incarcerat|prisi[oó]n|emprisonnement|'
        r'reclusione|pidana|penjara)\w*\b', text, re.I))
    has_forfeit = bool(re.search(
        r'\b(?:forfeit|confiscat|seiz|decomis|confiscaci|saisie|'
        r'confisca|sequestro|sitaan)\w*\b', text, re.I))
    if pen_hits >= 6: pen_score = 13
    elif pen_hits >= 3: pen_score = 9
    elif pen_hits >= 1: pen_score = 4
    if has_amounts: pen_score = min(22, pen_score + 3)
    if has_imprison: pen_score = min(22, pen_score + 3)
    if has_forfeit: pen_score = min(22, pen_score + 3)

    # ---- 3. Enforcement Authority (0-17) ----
    enf_score = 0
    enf_hits = count_pattern_matches(text, ENFORCEMENT_AUTHORITY_PATTERNS)
    has_boarding = bool(re.search(
        r'\bboard\w*\b.*\bvessel\b|\bvessel\b.*\bboard\w*\b|'
        r'\babord\w*\b.*\b(?:embarcaci|buque|navire|nave)\b',
        text, re.I))
    has_arrest = bool(re.search(
        r'\b(?:arrest|deten\w+|aprehend\w+|arr[eê]t\w*)\b', text, re.I))
    has_designated = bool(re.search(
        r'\b(?:authorized|designated|appointed|autoriz\w+|design\w+|'
        r'habilit\w+)\s+\w*\s*(?:officer|oficial|agent|funzionario|petugas)\b',
        text, re.I))
    if enf_hits >= 5: enf_score = 10
    elif enf_hits >= 3: enf_score = 7
    elif enf_hits >= 1: enf_score = 4
    if has_boarding: enf_score = min(17, enf_score + 2)
    if has_arrest: enf_score = min(17, enf_score + 3)
    if has_designated: enf_score = min(17, enf_score + 2)

    # ---- 4. Technology Provisions (0-22) ----
    tech_score = 0
    tech_hits = count_pattern_matches(text, TECHNOLOGY_PATTERNS)
    tech_mandated = bool(re.search(
        r'(?:shall|must|required|deber[áa]|obligatori|doi(?:t|vent)|wajib)'
        r'\s+\w*\s*(?:VMS|AIS|transponder|tracking|satellite|monitoring|'
        r'sat[eé]lit|monitoreo|rastreo|pemantau)',
        text, re.I))
    tech_mentioned = bool(re.search(
        r'\b(?:VMS|AIS|vessel\s+monitoring|satellite|transponder|'
        r'sistema\s+de\s+(?:monitoreo|seguimiento|localizaci)|'
        r'syst[eè]me\s+de\s+(?:surveillance|localisation))\b',
        text, re.I))
    if tech_hits >= 5: tech_score = 13
    elif tech_hits >= 3: tech_score = 9
    elif tech_hits >= 1: tech_score = 4
    if tech_mandated: tech_score = min(22, tech_score + 7)
    elif tech_mentioned: tech_score = min(22, tech_score + 3)

    # ---- 5. Liability Framework (0-17) ----
    liab_score = 0
    liab_hits = count_pattern_matches(text, LIABILITY_PATTERNS)
    has_joint = bool(re.search(
        r'\bjoint(?:ly)?\b.*\bliab\w+\b|\bsolidar\w+\b.*\bresponsab\w+\b',
        text, re.I))
    has_strict = bool(re.search(
        r'\bstrict\s+liability\b|\bresponsabilidad\s+objetiva\b', text, re.I))
    has_owner = bool(re.search(
        r'\b(?:owner|operator|master|propietario|armador|propri[eé]taire|'
        r'armatore|pemilik)\b.*\b(?:liab\w+|responsab\w+|tanggung)\b',
        text, re.I))
    if liab_hits >= 5: liab_score = 10
    elif liab_hits >= 3: liab_score = 7
    elif liab_hits >= 1: liab_score = 4
    if has_joint or has_strict: liab_score = min(17, liab_score + 3)
    if has_owner: liab_score = min(17, liab_score + 4)

    # Fisheries relevance penalty
    if not is_fisheries:
        ev_score = min(ev_score, 7)
        tech_score = min(tech_score, 7)
        enf_score = min(enf_score, 7)

    total = ev_score + pen_score + enf_score + tech_score + liab_score

    return {
        'evidence_score': ev_score,
        'penalty_score': pen_score,
        'enforcement_score': enf_score,
        'technology_score': tech_score,
        'liability_score': liab_score,
        'total_score': total,
        'n_sentences': len(sentences),
        'is_fisheries': is_fisheries,
    }


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def process_regulations():
    """Process all MPA regulation texts and produce scored CSV + statistics."""
    print("=" * 70)
    print("INDEX 1: REGULATION PREPAREDNESS (9,740 MPA zonations)")
    print("=" * 70)

    print("  Loading regulation data...")
    with open(DATA_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    print(f"  Loaded {len(rows):,} zonations from {len(set(r.get('country','') for r in rows))} countries")

    print("  Scoring with sentence-level legal text analysis...")
    results = []
    for i, row in enumerate(rows):
        if (i + 1) % 2000 == 0:
            print(f"    {i + 1:,} / {len(rows):,}...")

        scores = score_regulation(
            row.get('restrictions', ''),
            row.get('allowed', ''),
            row.get('definitions', ''),
            row.get('report_violations', ''),
        )

        results.append({
            'site_id': row.get('site_id', ''),
            'country': row.get('country', ''),
            'site_name': row.get('site_name', ''),
            **scores,
        })

    # Write regulation scores
    out_path = os.path.join(OUTPUT_DIR, "regulation_scores.csv")
    fields = list(results[0].keys())
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    # Statistics
    scores_list = [r['preparedness_score'] for r in results]
    mean_score = sum(scores_list) / len(scores_list)
    sorted_scores = sorted(scores_list)
    n = len(sorted_scores)
    median_score = sorted_scores[n // 2]
    sd_score = math.sqrt(sum((x - mean_score) ** 2 for x in scores_list) / n)
    pct_low = sum(1 for x in scores_list if x <= 30) / n * 100
    pct_high = sum(1 for x in scores_list if x >= 70) / n * 100

    improved = [r['improved_score'] for r in results]
    mean_improved = sum(improved) / len(improved)
    mean_improvement = mean_improved - mean_score
    pct_increase = (mean_improvement / mean_score * 100) if mean_score > 0 else 0

    print(f"\n  Results saved: {out_path}")
    print(f"  Mean Regulation Preparedness Index: {mean_score:.1f} / 100")
    print(f"  Median: {median_score:.1f}")
    print(f"  Score <= 30 (poorly prepared): {pct_low:.1f}%")
    print(f"  Score >= 70 (well prepared): {pct_high:.1f}%")
    print(f"  Mean after fixes: {mean_improved:.1f} (+{pct_increase:.0f}%)")

    # Country summary
    by_country = defaultdict(list)
    for r in results:
        by_country[r['country']].append(r)

    print(f"\n  {'Country':25s} | {'Mean':>6s} | {'Median':>6s} | {'N':>6s} | {'%Prohib':>7s} | {'%MonTech':>8s}")
    print("  " + "-" * 70)
    country_rows = []
    for country in sorted(by_country, key=lambda c: sum(r['preparedness_score'] for r in by_country[c]) / len(by_country[c]), reverse=True):
        recs = by_country[country]
        c_scores = [r['preparedness_score'] for r in recs]
        c_mean = sum(c_scores) / len(c_scores)
        c_sorted = sorted(c_scores)
        c_median = c_sorted[len(c_sorted) // 2]
        pct_prohib = sum(1 for r in recs if r['has_prohibition']) / len(recs) * 100
        pct_mon = sum(1 for r in recs if r['has_monitoring_reference']) / len(recs) * 100
        print(f"  {country:25s} | {c_mean:5.1f} | {c_median:5.1f} | {len(recs):6d} | {pct_prohib:6.1f}% | {pct_mon:7.1f}%")
        country_rows.append({
            'country': country, 'n_sites': len(recs),
            'mean_preparedness': round(c_mean, 1),
            'median_preparedness': round(c_median, 1),
            'pct_with_prohibition': round(pct_prohib, 1),
            'pct_with_monitoring': round(pct_mon, 1),
            'pct_with_reporting': round(sum(1 for r in recs if r['has_reporting_requirement']) / len(recs) * 100, 1),
            'mean_improvement': round(sum(r['max_improvement'] for r in recs) / len(recs), 1),
            'mean_after_fixes': round(sum(r['improved_score'] for r in recs) / len(recs), 1),
        })

    # Save country summary
    cs_path = os.path.join(OUTPUT_DIR, "derived/country_summary.csv")
    os.makedirs(os.path.dirname(cs_path), exist_ok=True)
    with open(cs_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(country_rows[0].keys()))
        writer.writeheader()
        writer.writerows(country_rows)

    # Save fix impact summary
    fix_counts = defaultdict(int)
    for r in results:
        for fix in r['applicable_fixes'].split(','):
            if fix:
                fix_counts[fix] += 1
    fix_impacts = {
        'clear_prohibition': 20, 'remove_discretion': 15, 'vessel_id': 10,
        'monitoring_reference': 10, 'reporting_requirement': 10,
        'temporal_scope': 5, 'evidence_pathway': 5,
    }
    fix_rows = []
    for fix_name in sorted(fix_counts, key=lambda f: fix_counts[f] * fix_impacts.get(f, 0), reverse=True):
        fix_rows.append({
            'fix_name': fix_name,
            'impact_per_site': fix_impacts.get(fix_name, 0),
            'n_sites_applicable': fix_counts[fix_name],
            'pct_sites_applicable': round(fix_counts[fix_name] / n * 100, 1),
        })
    fix_path = os.path.join(OUTPUT_DIR, "derived/fix_impact_summary.csv")
    with open(fix_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(fix_rows[0].keys()))
        writer.writeheader()
        writer.writerows(fix_rows)

    # Save manuscript statistics JSON
    stats = {
        "analysis_date": "2026-09-02",
        "sample": {
            "n_mpas": n,
            "n_countries": len(by_country),
            "countries": sorted(by_country.keys()),
        },
        "current_state": {
            "mean_preparedness": round(mean_score, 1),
            "median_preparedness": round(median_score, 1),
            "sd_preparedness": round(sd_score, 1),
            "pct_poorly_prepared": round(pct_low, 1),
            "pct_well_prepared": round(pct_high, 1),
        },
        "language_analysis": {
            "pct_with_prohibition": round(sum(1 for r in results if r['has_prohibition']) / n * 100, 1),
            "pct_with_monitoring_ref": round(sum(1 for r in results if r['has_monitoring_reference']) / n * 100, 1),
            "pct_with_evidence_pathway": round(sum(1 for r in results if r['has_evidence_pathway']) / n * 100, 1),
            "pct_with_vessel_ref": round(sum(1 for r in results if r['has_vessel_reference']) / n * 100, 1),
            "pct_with_reporting_req": round(sum(1 for r in results if r['has_reporting_requirement']) / n * 100, 1),
            "pct_with_ambiguous": round(sum(1 for r in results if r['n_discretionary'] > 0) / n * 100, 1),
        },
        "improvement_potential": {
            "mean_improvement": round(mean_improvement, 1),
            "mean_after_fixes": round(mean_improved, 1),
            "pct_increase": round(pct_increase, 1),
        },
    }
    with open(os.path.join(OUTPUT_DIR, "manuscript_statistics.json"), 'w') as f:
        json.dump(stats, f, indent=2)

    return results


def process_legislation():
    """Process all legislation documents and produce scored CSVs."""
    print("\n" + "=" * 70)
    print("INDEX 2: LEGISLATION READINESS (119 FAOLEX documents)")
    print("=" * 70)

    if not os.path.isdir(TEXT_DIR):
        print(f"  ERROR: Text directory not found: {TEXT_DIR}")
        return [], []

    files = sorted(os.listdir(TEXT_DIR))
    pdf_files = [f for f in files if f.endswith('.pdf')]
    txt_files = [f for f in files if f.endswith('.txt')]
    print(f"  Found {len(pdf_files)} PDFs and {len(txt_files)} TXT files")

    # English translations override
    translated = {}
    for txt in txt_files:
        if '_EN.txt' in txt:
            translated[txt.replace('_EN.txt', '.pdf')] = txt

    results = []
    for filename in pdf_files:
        filepath = os.path.join(TEXT_DIR, filename)

        if filename in translated:
            en_path = os.path.join(TEXT_DIR, translated[filename])
            with open(en_path, encoding='utf-8') as f:
                text = f.read()
        else:
            text = extract_text_from_pdf(filepath)

        if not text or len(text.strip()) < 50:
            continue

        iso3 = filename[:3].upper()
        scores = score_legislation(text)
        results.append({
            'filename': filename,
            'iso3': iso3,
            **scores,
        })

    # Save per-document scores
    out_path = os.path.join(OUTPUT_DIR, "legislation_scores.csv")
    if results:
        fields = list(results[0].keys())
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(results)
        print(f"  Saved {len(results)} document scores: {out_path}")

    # Country-level aggregation (best score per dimension)
    by_country = defaultdict(list)
    for r in results:
        by_country[r['iso3']].append(r)

    country_results = []
    for iso3 in sorted(by_country):
        docs = by_country[iso3]
        best = {
            'iso3': iso3,
            'country': COUNTRY_NAMES.get(iso3, iso3),
            'n_documents': len(docs),
            'evidence_score': max(d['evidence_score'] for d in docs),
            'penalty_score': max(d['penalty_score'] for d in docs),
            'enforcement_score': max(d['enforcement_score'] for d in docs),
            'technology_score': max(d['technology_score'] for d in docs),
            'liability_score': max(d['liability_score'] for d in docs),
            'n_fisheries_relevant': sum(1 for d in docs if d['is_fisheries']),
        }
        best['total_score'] = (best['evidence_score'] + best['penalty_score'] +
                               best['enforcement_score'] + best['technology_score'] +
                               best['liability_score'])
        country_results.append(best)

    # Save country scores
    c_out = os.path.join(OUTPUT_DIR, "legislation_country_scores.csv")
    if country_results:
        fields = list(country_results[0].keys())
        with open(c_out, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(country_results)

    # Print summary
    print(f"\n  {'Country':25s} | {'Score':>6s} | {'Evid':>5s} | {'Pen':>5s} | {'Enf':>5s} | {'Tech':>5s} | {'Liab':>5s} | {'Fish':>5s}")
    print("  " + "-" * 75)
    for cr in sorted(country_results, key=lambda x: x['total_score'], reverse=True):
        print(f"  {cr['country']:25s} | {cr['total_score']:5.0f} | {cr['evidence_score']:5.0f} | "
              f"{cr['penalty_score']:5.0f} | {cr['enforcement_score']:5.0f} | {cr['technology_score']:5.0f} | "
              f"{cr['liability_score']:5.0f} | "
              f"{cr['n_fisheries_relevant']:3d}/{cr['n_documents']}")

    scores = [cr['total_score'] for cr in country_results]
    if scores:
        mean_leg = sum(scores) / len(scores)
        sorted_s = sorted(scores)
        median_leg = sorted_s[len(sorted_s) // 2]
        best_c = max(country_results, key=lambda x: x['total_score'])
        worst_c = min(country_results, key=lambda x: x['total_score'])

        print(f"\n  Mean Legislation Readiness Index: {mean_leg:.1f} / 100")
        print(f"  Median: {median_leg:.1f}")
        print(f"  Best: {best_c['country']} ({best_c['total_score']:.0f})")
        print(f"  Worst: {worst_c['country']} ({worst_c['total_score']:.0f})")

        # Legislation statistics JSON
        leg_stats = {
            "n_countries": len(country_results),
            "n_documents": len(results),
            "mean_score": round(mean_leg, 1),
            "median_score": round(median_leg, 1),
            "best_country": best_c['country'],
            "best_score": round(best_c['total_score'], 1),
            "worst_country": worst_c['country'],
            "worst_score": round(worst_c['total_score'], 1),
            "dimension_means": {
                "evidence": round(sum(c['evidence_score'] for c in country_results) / len(country_results), 1),
                "penalty": round(sum(c['penalty_score'] for c in country_results) / len(country_results), 1),
                "enforcement": round(sum(c['enforcement_score'] for c in country_results) / len(country_results), 1),
                "technology": round(sum(c['technology_score'] for c in country_results) / len(country_results), 1),
                "liability": round(sum(c['liability_score'] for c in country_results) / len(country_results), 1),
            },
        }
        with open(os.path.join(OUTPUT_DIR, "manuscript_legislation_statistics.json"), 'w') as f:
            json.dump(leg_stats, f, indent=2)

    return results, country_results


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "derived"), exist_ok=True)

    reg_results = process_regulations()
    leg_results, leg_country = process_legislation()

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"\nOutputs saved to: {OUTPUT_DIR}")
    print(f"  regulation_scores.csv             — {len(reg_results):,} MPA scores")
    print(f"  legislation_scores.csv            — {len(leg_results)} document scores")
    print(f"  legislation_country_scores.csv    — {len(leg_country)} country scores")
    print(f"  manuscript_statistics.json")
    print(f"  manuscript_legislation_statistics.json")
    print(f"  derived/country_summary.csv")
    print(f"  derived/fix_impact_summary.csv")


if __name__ == "__main__":
    main()
