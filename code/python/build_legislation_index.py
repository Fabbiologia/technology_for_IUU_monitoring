#!/usr/bin/env python3
"""
Build the Legislation Readiness Index for 15 countries.

Extracts text from downloaded FAOLEX PDFs, identifies relevant legislation,
and scores each country on prosecution readiness dimensions:
  - Evidence admissibility (satellite/electronic evidence provisions)
  - Penalty framework (clear penalties for fisheries violations)
  - Enforcement authority (powers of inspectors/officers)
  - Technology provisions (VMS/AIS/satellite monitoring mandates)
  - Liability framework (vessel owner/operator liability)
  - Legislative currency (how recently updated)

Output:
  - data/03_external/legislation/legislation_extracted_text.csv
  - data/03_external/legislation/legislation_readiness_scores.csv
  - outputs/latest/legislation_readiness_index.csv
  - outputs/latest/manuscript_legislation_statistics.json
"""

import os
import re
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# Try to import pdfplumber
try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber required. Install with: pip3 install pdfplumber")
    sys.exit(1)

ROOT_DIR = "/Volumes/bacdrive/Dropbox/Work/technology_for_IUU_monitoring"
TEXT_DIR = os.path.join(ROOT_DIR, "data/03_external/legislation/texts")
OUTPUT_DIR = os.path.join(ROOT_DIR, "data/03_external/legislation")
RESULTS_DIR = os.path.join(ROOT_DIR, "outputs/latest")
os.makedirs(RESULTS_DIR, exist_ok=True)

COUNTRIES = {
    "AUS": "Australia", "CAN": "Canada", "CHL": "Chile", "ECU": "Ecuador",
    "GAB": "Gabon", "GRC": "Greece", "IDN": "Indonesia", "ITA": "Italy",
    "MYS": "Malaysia", "MEX": "Mexico", "NZL": "New Zealand", "PAN": "Panama",
    "MDV": "Republic of Maldives", "ZAF": "South Africa", "ESP": "Spain",
}

# Known key legislation — manual metadata for the primary fisheries laws
# This enriches whatever the API returned with proper titles and dates
KEY_LEGISLATION_META = {
    "aus102209": {"title": "Fisheries Legislation Amendment Act 2010", "year": 2010, "category": "primary_fisheries"},
    "aus22421": {"title": "Crimes at Sea Act 2000", "year": 2000, "category": "enforcement"},
    "can80430": {"title": "Fisheries Act (R.S.C., 1985, c. F-14)", "year": 1985, "category": "primary_fisheries", "last_amended": 2019},
    "ecu155376": {"title": "Reglamento Ley Orgánica Pesca y Acuicultura", "year": 2020, "category": "primary_fisheries"},
    "ecu18902": {"title": "Ley de Pesca y Desarrollo Pesquero", "year": 1974, "category": "primary_fisheries"},
    "spa67227": {"title": "Real Decreto Ley de Pesca", "year": 2001, "category": "primary_fisheries"},
    "spa1435": {"title": "Ley de Costas", "year": 1988, "category": "environment_mpa"},
    "gab4352": {"title": "Loi relative à la protection du milieu marin", "year": 2005, "category": "environment_mpa"},
    "gab4861": {"title": "Décret pêche maritime", "year": 2005, "category": "primary_fisheries"},
    "gab1187": {"title": "Loi portant Code des pêches", "year": 2005, "category": "primary_fisheries"},
    "gre23292": {"title": "Legislative Decree on Marine Fisheries", "year": 1970, "category": "primary_fisheries"},
    "gre30398": {"title": "Law on Fisheries Management", "year": 1970, "category": "primary_fisheries"},
    "ins6881": {"title": "Fisheries Ordinance", "year": 1985, "category": "primary_fisheries"},
    "ins48793": {"title": "Government Regulation on Fisheries", "year": 2001, "category": "primary_fisheries"},
    "ita64213": {"title": "Decreto Legislativo recante riordino pesca", "year": 2012, "category": "primary_fisheries"},
    "ita38677": {"title": "Legge sulla pesca marittima", "year": 1982, "category": "primary_fisheries"},
    "mdv195984": {"title": "Fisheries Act of the Maldives (Act No. 14/2019)", "year": 2019, "category": "primary_fisheries"},
    "MDV232166": {"title": "Maldives Fisheries Regulation", "year": 2020, "category": "primary_fisheries"},
    "mal1871": {"title": "Fisheries Act 1985 (Act 317)", "year": 1985, "category": "primary_fisheries"},
    "mal157994": {"title": "Fisheries (Maritime) Regulations", "year": 2019, "category": "primary_fisheries"},
    "mex1346": {"title": "Ley General de Pesca y Acuacultura Sustentables", "year": 2007, "category": "primary_fisheries"},
    "mex5738": {"title": "Ley General del Equilibrio Ecológico", "year": 1988, "category": "environment_mpa"},
    "mex3466": {"title": "Ley Federal del Mar", "year": 1986, "category": "maritime"},
    "nze1986": {"title": "Fisheries Act 1996", "year": 1996, "category": "primary_fisheries"},
    "nze1973": {"title": "Marine Reserves Act 1971", "year": 1971, "category": "environment_mpa"},
    "nze70790": {"title": "Fisheries (Infringement Offences) Regulations", "year": 2001, "category": "enforcement"},
    "saf91270": {"title": "Marine Living Resources Act 1998", "year": 1998, "category": "primary_fisheries"},
    "saf45032": {"title": "National Environmental Management: Protected Areas Act", "year": 2003, "category": "environment_mpa"},
    "saf90450": {"title": "National Environmental Management: Biodiversity Act", "year": 2004, "category": "environment_mpa"},
}


# ============================================================================
# Scoring dimensions for Legislation Readiness
# ============================================================================

# Each dimension has keyword patterns and a max score
DIMENSIONS = {
    "evidence_admissibility": {
        "description": "Accepts satellite/electronic/technological evidence",
        "max_score": 20,
        "keywords": [
            # English
            r"\b(satellite|remote sensing|electronic)\b.{0,30}\b(evidence|proof|admiss)",
            r"\bevidence\b.{0,40}\b(electronic|digital|technolog|satellite|sensor|device)",
            r"\b(VMS|AIS|vessel monitoring)\b.{0,30}\b(data|evidence|record|proof)",
            r"\b(admissi|accept|valid)\w*\b.{0,30}\b(evidence|proof|data)\b",
            r"\b(photogra|video|image|recording)\b.{0,30}\b(evidence|proof|admiss)",
            r"\belectronic\s+(monitoring|surveillance|record)",
            r"\bproof\b.{0,30}\b(violation|offence|offense|infraction)",
            # Spanish (Ecuador, Chile, Mexico, Spain, Panama)
            r"\b(prueba|evidencia|medio\s+probatorio)\b.{0,30}\b(electr|digital|tecnol|sat[eé]lit)",
            r"\b(sat[eé]lite|electr[oó]nic|digital)\b.{0,30}\b(prueba|evidencia|dato|registro)",
            r"\b(admisi|acepta|v[aá]lid)\w*\b.{0,30}\b(prueba|evidencia|dato)\b",
            r"\b(fotograf|video|imagen|grabaci)\b.{0,30}\b(prueba|evidencia)",
            r"\bmonitoreo\s+electr[oó]nico\b",
            # French (Gabon)
            r"\b(preuve|[eé]l[eé]ment\s+de\s+preuve)\b.{0,30}\b(électronique|numérique|satellite|technolog)",
            r"\b(satellite|[eé]lectronique|num[eé]rique)\b.{0,30}\b(preuve|donn[eé]e|surveillance)",
            r"\b(admissi|accepta|recevab)\w*\b.{0,30}\b(preuve|donn[eé]e)\b",
            r"\bsurveillance\s+[eé]lectronique\b",
            # Italian
            r"\b(prova|elemento\s+di\s+prova)\b.{0,30}\b(elettronic|digitale|satellite|tecnolog)",
            r"\b(satellite|elettronic|digitale)\b.{0,30}\b(prova|dato|monitoraggio)",
            r"\b(ammissibil|accettabil|valid)\w*\b.{0,30}\b(prova|dato|elemento)\b",
            # Indonesian (Bahasa)
            r"\b(bukti|pembuktian)\b.{0,30}\b(elektronik|digital|satelit|teknolog)",
            r"\b(satelit|elektronik|digital)\b.{0,30}\b(bukti|data|pemantauan)",
        ],
        "strong_keywords": [
            r"\b(satellite|VMS|AIS|electronic).{0,20}(evidence|proof).{0,20}(admiss|accept|valid)",
            r"\bevidence\b.{0,20}(shall|must|is)\b.{0,20}(admiss|accept|valid)",
            r"\b(prueba|evidencia).{0,20}(sat[eé]lit|electr|VMS|AIS).{0,20}(admisi|v[aá]lid|acepta)",
            r"\b(preuve).{0,20}(satellite|[eé]lectronique|VMS).{0,20}(admissi|recevab)",
        ]
    },
    "penalty_framework": {
        "description": "Clear penalties for fisheries/MPA violations",
        "max_score": 20,
        "keywords": [
            # English
            r"\b(fine|penalty|penalt|sanction)\b.{0,30}\b(fish|vessel|marine|MPA|protect)",
            r"\b(imprison|jail|detention|custod)\b.{0,30}\b(fish|vessel|marine|offence|offense)",
            r"\b(confiscat|seiz|forfeit)\b.{0,30}\b(vessel|catch|gear|equipment)",
            r"\b(suspend|revok|cancel)\b.{0,30}\b(licen[cs]e|permit|authoriz)",
            r"\b(offence|offense|violation|infraction|contravention)\b",
            r"\b(prohibit|forbidden|illegal|unlawful)\b.{0,30}\b(fish|trawl|harvest|catch)",
            r"\$\s*\d{1,3}[,.]?\d{3,}",
            r"\b\d{1,3}[,.]?\d{3,}\s*(dollar|peso|euro|rand|rupiah|ringgit)",
            # Spanish
            r"\b(multa|sanci[oó]n|penalidad|pena)\b.{0,30}\b(pesca|buque|embarcaci|marino|mar)",
            r"\b(prisi[oó]n|encarcelam|reclusi[oó]n|arresto)\b.{0,30}\b(pesca|buque|infracci)",
            r"\b(confisca|decomis|incauta)\b.{0,30}\b(embarcaci|buque|captura|equipo|arte)",
            r"\b(suspende|revoca|cancela)\b.{0,30}\b(licencia|permiso|autorizaci)",
            r"\b(infracci[oó]n|delito|violaci[oó]n|contravenci[oó]n|falta)\b",
            r"\b(prohib|ilegal|il[ií]cit|vedado|veda)\b.{0,30}\b(pesc|captur|extracc)",
            # French
            r"\b(amende|sanction|peine|p[eé]nalit[eé])\b.{0,30}\b(p[eê]che|navire|marin|prot[eé]g)",
            r"\b(emprisonnement|prison|d[eé]tention|r[eé]clusion)\b.{0,30}\b(p[eê]che|navire|infract)",
            r"\b(confisqu|saisie|saisi)\b.{0,30}\b(navire|capture|engin|[eé]quipement)",
            r"\b(suspend|r[eé]voqu|annul)\b.{0,30}\b(licence|permis|autoris)",
            r"\b(infraction|d[eé]lit|contravention)\b",
            r"\b(interdi|ill[eé]gal|illicite)\b.{0,30}\b(p[eê]che|capture)",
            # Italian
            r"\b(multa|sanzione|pena|ammenda)\b.{0,30}\b(pesca|nave|imbarcazione|marino)",
            r"\b(reclusione|arresto|detenzione)\b.{0,30}\b(pesca|nave|infrazione|reato)",
            r"\b(confisca|sequestr|requisiz)\b.{0,30}\b(nave|imbarcazione|cattura|attrezz)",
            r"\b(sospend|revoca|annulla)\b.{0,30}\b(licenza|permesso|autorizzaz)",
            r"\b(infrazione|reato|violazione|contravvenzione)\b",
            r"\b(divieto|vietato|illecito|illegale)\b.{0,30}\b(pesca|cattura)",
            # Indonesian
            r"\b(denda|sanksi|pidana|hukuman)\b.{0,30}\b(perikanan|kapal|laut|ikan)",
            r"\b(penjara|kurungan|penahanan)\b.{0,30}\b(perikanan|kapal|pelanggaran)",
            r"\b(sita|rampas|penyitaan)\b.{0,30}\b(kapal|hasil|alat|peralatan)",
            r"\b(pelanggaran|tindak\s+pidana|kejahatan)\b",
            r"\b(dilarang|larangan|ilegal|melawan\s+hukum)\b.{0,30}\b(ikan|tangkap|perikanan)",
        ],
        "strong_keywords": [
            r"\b(penalty|fine)\b.{0,20}\b(not exceed|maximum|minimum)\b.{0,20}\d+",
            r"\b(imprison|custod)\b.{0,20}\b(not exceed|maximum|year|month)",
            r"\b(multa|sanci[oó]n)\b.{0,20}\b(m[aá]xim|m[ií]nim)\b.{0,20}\d+",
            r"\b(amende|peine)\b.{0,20}\b(maximum|minimum)\b.{0,20}\d+",
            r"\b(denda|pidana)\b.{0,20}\b(paling|maksim|minim)\b.{0,20}\d+",
        ]
    },
    "enforcement_authority": {
        "description": "Clear enforcement powers and inspection authority",
        "max_score": 15,
        "keywords": [
            # English
            r"\b(inspect|officer|authoriz\w+ person|enforcement agent)\b",
            r"\b(board|enter|search|stop)\b.{0,30}\b(vessel|boat|ship|premis)",
            r"\b(power|authority|duty)\b.{0,30}\b(inspect|enforce|investigat|arrest|detain)",
            r"\b(seize|confiscat|impound|detain)\b.{0,30}\b(vessel|catch|gear|fish|evidence)",
            r"\b(arrest|apprehend|detain)\b.{0,30}\b(person|individual|master|captain|owner)",
            r"\b(coast\s*guard|navy|maritime\s*(police|authority|patrol))\b",
            r"\b(surveillance|patrol|monitor)\b.{0,30}\b(zone|area|water|sea|EEZ)",
            # Spanish
            r"\b(inspector|funcionario|agente|autoridad\s+competente)\b",
            r"\b(abordar|ingresar|registrar|detener)\b.{0,30}\b(embarcaci|buque|nave|local)",
            r"\b(facultad|poder|autoridad|competencia)\b.{0,30}\b(inspeccio|fiscaliz|investig|arrest|deten)",
            r"\b(incauta|decomis|confisca|embarg)\b.{0,30}\b(embarcaci|buque|captura|arte|pesca)",
            r"\b(guardia\s*costera|armada|autoridad\s+mar[ií]tima|capitan[ií]a)\b",
            r"\b(vigilancia|patrullaje|control)\b.{0,30}\b(zona|[aá]rea|agua|mar|ZEE)",
            # French
            r"\b(inspecteur|agent|fonctionnaire|autorit[eé]\s+comp[eé]tente)\b",
            r"\b(monter\s+[aà]\s+bord|p[eé]n[eé]trer|fouiller|arr[eê]ter)\b.{0,30}\b(navire|bateau|local)",
            r"\b(pouvoir|autorit[eé]|comp[eé]tence)\b.{0,30}\b(inspect|contr[oô]l|recherch|arr[eê]t)",
            r"\b(saisir|confisqu|immobilis)\b.{0,30}\b(navire|capture|engin|p[eê]che)",
            r"\b(garde\s*c[oô]te|marine\s+nationale|gendarmerie\s+maritime)\b",
            r"\b(surveillance|patrouille|contr[oô]le)\b.{0,30}\b(zone|eaux|mer|ZEE)",
            # Italian
            r"\b(ispettore|ufficiale|agente|autorit[aà]\s+competente|guardia)\b",
            r"\b(salire\s+a\s+bordo|accedere|perquisire|fermare)\b.{0,30}\b(nave|imbarcazione|locale)",
            r"\b(potere|autorit[aà]|competenza)\b.{0,30}\b(ispezion|control|indagin|arrest)",
            r"\b(sequestr|confisca|ferm)\b.{0,30}\b(nave|imbarcazione|cattura|attrezz|pesca)",
            r"\b(guardia\s+costiera|capitaneria|marina\s+militare)\b",
            # Indonesian
            r"\b(penyidik|petugas|pengawas|pejabat)\b",
            r"\b(memeriksa|memasuki|menggeledah|menghentikan)\b.{0,30}\b(kapal|perahu|tempat)",
            r"\b(wewenang|kewenangan|tugas)\b.{0,30}\b(periksa|awas|sidik|tangkap|tahan)",
            r"\b(menyita|merampas|menahan)\b.{0,30}\b(kapal|hasil|alat|ikan|bukti)",
            r"\b(TNI\s+AL|angkatan\s+laut|polisi\s+air|PSDKP)\b",
        ],
        "strong_keywords": [
            r"\b(officer|inspector)\b.{0,30}\b(may|shall|power)\b.{0,30}\b(board|enter|search|seize)",
            r"\b(inspector|funcionario)\b.{0,30}\b(podr[aá]|deber[aá]|facultad)\b.{0,30}\b(abordar|registrar|incautar)",
            r"\b(agent|inspecteur)\b.{0,30}\b(peut|doit|pouvoir)\b.{0,30}\b(bord|fouiller|saisir)",
        ]
    },
    "technology_provisions": {
        "description": "Mandates for VMS/AIS/satellite monitoring technology",
        "max_score": 20,
        "keywords": [
            # English
            r"\b(VMS|vessel\s+monitoring\s+system)\b",
            r"\b(AIS|automatic\s+identification\s+system)\b",
            r"\b(satellite|remote\s+sens|GPS|transponder)\b.{0,30}\b(monitor|track|locat|surveil)",
            r"\b(electronic|digital)\b.{0,30}\b(logbook|report|monitoring|record|device)",
            r"\b(tracking|monitoring)\s+(device|system|equipment|technology)\b",
            r"\b(observer|camera)\b.{0,30}\b(board|vessel|fishing)\b",
            r"\b(transmit|broadcast|signal)\b.{0,30}\b(position|location|identif)\b",
            # Spanish
            r"\b(VMS|sistema\s+de\s+monitoreo\s+de\s+embarcaciones)\b",
            r"\b(AIS|sistema\s+de\s+identificaci[oó]n\s+autom[aá]tic)\b",
            r"\b(sat[eé]lite|sensor\s+remoto|GPS|transpondedor)\b.{0,30}\b(monitoreo|rastreo|localiz|vigil)",
            r"\b(electr[oó]nic|digital)\b.{0,30}\b(bit[aá]cora|informe|monitoreo|registro|dispositiv)",
            r"\b(rastreo|monitoreo|seguimiento)\s+(dispositiv|sistema|equipo|tecnolog)\b",
            r"\b(observador|c[aá]mara)\b.{0,30}\b(bordo|embarcaci|pesca)\b",
            r"\b(transmitir|emitir|se[nñ]al)\b.{0,30}\b(posici[oó]n|ubicaci[oó]n|identific)\b",
            # French
            r"\b(VMS|syst[eè]me\s+de\s+surveillance\s+des\s+navires)\b",
            r"\b(AIS|syst[eè]me\s+d.identification\s+automatique)\b",
            r"\b(satellite|t[eé]l[eé]d[eé]tection|GPS|transpondeur)\b.{0,30}\b(surveillance|suivi|localis|pistage)",
            r"\b([eé]lectronique|num[eé]rique)\b.{0,30}\b(journal|rapport|surveillance|registre|dispositif)",
            r"\b(observateur|cam[eé]ra)\b.{0,30}\b(bord|navire|p[eê]che)\b",
            # Italian
            r"\b(VMS|sistema\s+di\s+monitoraggio\s+(delle\s+)?navi)\b",
            r"\b(AIS|sistema\s+di\s+identificazione\s+automatic)\b",
            r"\b(satellite|telerilevamento|GPS|transponder)\b.{0,30}\b(monitoraggio|tracciamento|localizzaz|sorveglianza)",
            r"\b(elettronic|digitale)\b.{0,30}\b(giornale|rapporto|monitoraggio|registro|dispositiv)",
            # Indonesian
            r"\b(VMS|sistem\s+pemantauan\s+kapal)\b",
            r"\b(AIS|sistem\s+identifikasi\s+otomatis)\b",
            r"\b(satelit|penginderaan\s+jauh|GPS|transponder)\b.{0,30}\b(pemantauan|pelacakan|lokasi|pengawasan)",
            r"\b(elektronik|digital)\b.{0,30}\b(logbook|laporan|pemantauan|catatan|perangkat)",
        ],
        "strong_keywords": [
            r"\b(VMS|AIS)\b.{0,20}(require|mandator|shall|must|obligat)",
            r"\b(vessel|boat|ship)\b.{0,20}(shall|must|require)\b.{0,20}(equip|carry|install).{0,20}(VMS|AIS|transponder|tracking)",
            r"\b(VMS|AIS)\b.{0,20}(obligat|deber|requerir)",
            r"\b(embarcaci|buque|navire|kapal)\b.{0,20}(deber|obligat|wajib).{0,20}(VMS|AIS|transponder)",
        ]
    },
    "liability_framework": {
        "description": "Clear liability for vessel owners/operators/masters",
        "max_score": 15,
        "keywords": [
            # English
            r"\b(owner|operator|master|captain|skipper)\b.{0,30}\b(liable|responsib|accountab)",
            r"\b(liab|responsib)\w*\b.{0,30}\b(vessel|boat|ship|owner|operator|master)",
            r"\b(presume|deem)\w*\b.{0,30}\b(guilty|liable|responsib|offence|offense)",
            r"\b(joint|solidar|sever)\w*\b.{0,20}\b(liab|responsib)",
            r"\b(strict\s+liab|absolute\s+liab|vicarious\s+liab)\b",
            r"\b(beneficial\s+owner|flag\s+state)\b.{0,20}\b(responsib|liable|obligat)",
            # Spanish
            r"\b(propietario|armador|patr[oó]n|capit[aá]n|operador)\b.{0,30}\b(responsab|culpab)",
            r"\b(responsab)\w*\b.{0,30}\b(embarcaci|buque|propietario|armador|patr[oó]n)",
            r"\b(presum|consider)\w*\b.{0,30}\b(culpab|responsab|infracci)",
            r"\b(solidari|mancomunad)\w*\b.{0,20}\b(responsab)",
            # French
            r"\b(propri[eé]taire|armateur|patron|capitaine|exploitant)\b.{0,30}\b(responsab|coupab)",
            r"\b(responsab)\w*\b.{0,30}\b(navire|bateau|propri[eé]taire|armateur|patron)",
            r"\b(pr[eé]sum|consid[eé]r)\w*\b.{0,30}\b(coupab|responsab|infract)",
            r"\b(solidair|conjoint)\w*\b.{0,20}\b(responsab)",
            # Italian
            r"\b(proprietario|armatore|comandante|capitano|operatore)\b.{0,30}\b(responsabil|colpevol)",
            r"\b(responsabil)\w*\b.{0,30}\b(nave|imbarcazione|proprietario|armatore|comandante)",
            # Indonesian
            r"\b(pemilik|nahkoda|operator|nakhoda)\b.{0,30}\b(bertanggung\s*jawab|bersalah)",
            r"\b(tanggung\s*jawab)\w*\b.{0,30}\b(kapal|pemilik|nahkoda|operator)",
        ],
        "strong_keywords": [
            r"\b(owner|operator)\b.{0,20}(shall be|is|deemed)\b.{0,20}(liable|responsib)",
            r"\b(propietario|armador)\b.{0,20}(ser[aá]|es|consider)\b.{0,20}(responsab)",
            r"\b(propri[eé]taire|armateur)\b.{0,20}(sera|est|consid[eé]r)\b.{0,20}(responsab)",
        ]
    },
    "legislative_currency": {
        "description": "How recently the legislation was updated",
        "max_score": 10,
        # This is scored based on amendment dates, not keywords
        "keywords": [],
        "strong_keywords": []
    },
}


def extract_text_from_pdf(pdf_path):
    """Extract full text from a PDF (no page limit)."""
    try:
        text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
        return "\n".join(text)
    except Exception as e:
        return f"[ERROR: {e}]"


def identify_legislation(text, filename):
    """Try to identify the legislation from its content."""
    # Extract title from first few lines
    lines = text.split("\n")[:20]
    first_lines = " ".join(l.strip() for l in lines if l.strip())[:500]

    # Try to find year from title/header area
    year_match = re.search(r'\b(19[6-9]\d|20[0-2]\d)\b', first_lines)
    year = int(year_match.group(1)) if year_match else None

    # Search FULL text for amendment dates (not just first 5000 chars)
    # Cap at 2025 — PDFs were downloaded before 2026, so any "2026" is a future reference
    amend_years = re.findall(r'\b(19[6-9]\d|20[0-2]\d)\b', text)
    amend_years = [int(y) for y in amend_years if 1960 <= int(y) <= 2025]
    last_amended = max(amend_years) if amend_years else year

    return {
        "first_lines": first_lines[:300],
        "year": year,
        "last_amended": last_amended,
        "text_length": len(text),
        "page_count": text.count("\n\n") + 1,  # rough estimate
    }


# OCR-tolerant simple term lists per dimension (single words, no compound matching)
# These provide a baseline score that works even with degraded OCR text
SIMPLE_TERMS = {
    "evidence_admissibility": [
        "evidence", "proof", "admissib", "prueba", "evidencia", "probatorio",
        "preuve", "prova", "bukti", "pembuktian",
        "VMS", "AIS", "satellite", "sat.lit", "elettronic", "electr.nic",
        ".lectronique", "elektronik",
    ],
    "penalty_framework": [
        "penalty", "fine", "sanction", "imprison", "offence", "offense",
        "multa", "sanci", "pena", "prisi", "infracci", "delito",
        "amende", "peine", "emprisonnement", "infraction",
        "sanzione", "ammenda", "reclusione", "reato",
        "denda", "pidana", "penjara", "pelanggaran",
        "confiscat", "seiz", "forfeit", "decomis", "incauta",
        "confisqu", "saisie", "sequestr", "sita", "rampas",
    ],
    "enforcement_authority": [
        "inspector", "officer", "enforce", "authority", "patrol",
        "funcionario", "autoridad", "vigilancia", "capitan",
        "inspecteur", "agent", "gendarmerie", "garde",
        "ispettore", "guardia", "capitaneria",
        "penyidik", "pengawas", "pejabat", "petugas",
        "coast guard", "navy", "armada",
    ],
    "technology_provisions": [
        "VMS", "AIS", "GPS", "satellite", "transponder", "tracking",
        "monitoring system", "electronic logbook", "observer",
        "monitoreo", "rastreo", "sat.lite", "seguimiento",
        "surveillance", "t.l.d.tection", "dispositif",
        "monitoraggio", "tracciamento",
        "pemantauan", "pelacakan", "satelit",
    ],
    "liability_framework": [
        "liable", "liability", "responsible", "owner", "operator",
        "responsab", "propietario", "armador",
        "propri.taire", "armateur",
        "proprietario", "armatore",
        "pemilik", "nahkoda", "tanggung jawab",
    ],
}


def score_dimension(text, dimension_config, dim_name=None):
    """Score text on a single dimension using keyword matching."""
    if not dimension_config["keywords"] and dim_name not in SIMPLE_TERMS:
        return 0, 0, []

    text_lower = text.lower()
    max_score = dimension_config["max_score"]

    # Phase 1: Simple term presence (OCR-tolerant baseline)
    simple_score = 0
    if dim_name and dim_name in SIMPLE_TERMS:
        simple_hits = 0
        for term in SIMPLE_TERMS[dim_name]:
            if re.search(term.lower(), text_lower):
                simple_hits += 1
        # Simple terms give up to 50% of max score
        if simple_hits >= 5:
            simple_score = max_score * 0.5
        elif simple_hits >= 3:
            simple_score = max_score * 0.3
        elif simple_hits >= 1:
            simple_score = max_score * 0.15

    # Phase 2: Compound keyword matches (higher quality signal)
    matches = []
    for pattern in dimension_config["keywords"]:
        try:
            found = re.findall(pattern, text_lower, re.IGNORECASE)
            if found:
                matches.extend(found[:3])  # Cap at 3 per pattern
        except re.error:
            pass

    # Strong keyword matches (bonus)
    strong_matches = 0
    for pattern in dimension_config["strong_keywords"]:
        try:
            found = re.findall(pattern, text_lower, re.IGNORECASE)
            strong_matches += len(found)
        except re.error:
            pass

    # Compound scoring
    n_matches = len(matches)
    if n_matches == 0:
        compound_score = 0
    elif n_matches <= 2:
        compound_score = max_score * 0.3
    elif n_matches <= 5:
        compound_score = max_score * 0.5
    elif n_matches <= 10:
        compound_score = max_score * 0.7
    elif n_matches <= 20:
        compound_score = max_score * 0.85
    else:
        compound_score = max_score * 0.9

    # Strong keyword bonus (up to max)
    if strong_matches > 0:
        compound_score = min(max_score, compound_score + max_score * 0.1 * min(strong_matches, 3))

    # Final score: take the BETTER of simple baseline or compound score
    score = max(simple_score, compound_score)

    return round(score, 1), n_matches, matches[:5]


def score_currency(year, last_amended):
    """Score legislative currency (how recently updated). Max 10 points."""
    current_year = 2026
    if last_amended is None and year is None:
        return 0
    ref_year = last_amended or year
    age = current_year - ref_year

    if age <= 3:
        return 10
    elif age <= 5:
        return 8
    elif age <= 10:
        return 6
    elif age <= 15:
        return 4
    elif age <= 25:
        return 2
    else:
        return 0


def main():
    print("=" * 70)
    print("LEGISLATION READINESS INDEX BUILDER")
    print("=" * 70)

    # Step 1: Extract text from all PDFs (and translated .txt files)
    print("\n--- Step 1: Extracting text from PDFs ---")
    pdf_files = sorted(f for f in os.listdir(TEXT_DIR) if f.endswith(".pdf"))
    # Also find translated text files (e.g., GRC_gre23292_EN.txt)
    translated_files = {f.split("_EN.txt")[0]: f
                        for f in os.listdir(TEXT_DIR) if f.endswith("_EN.txt")}
    print(f"Found {len(pdf_files)} PDFs + {len(translated_files)} translated texts")

    # For Greek PDFs, prefer translated English text if available
    greek_pdfs_with_translation = set()
    for pdf_file in pdf_files:
        base = pdf_file.replace(".pdf", "")
        if base in translated_files:
            greek_pdfs_with_translation.add(pdf_file)

    extracted = []
    for i, pdf_file in enumerate(pdf_files):
        pdf_path = os.path.join(TEXT_DIR, pdf_file)
        iso3 = pdf_file.split("_")[0]

        if iso3 not in COUNTRIES:
            continue

        # Use English translation if available (for Greek texts)
        base = pdf_file.replace(".pdf", "")
        if base in translated_files:
            txt_path = os.path.join(TEXT_DIR, translated_files[base])
            print(f"  [{i+1}/{len(pdf_files)}] {pdf_file} (using EN translation)...",
                  end=" ", flush=True)
            with open(txt_path, "r", encoding="utf-8") as f:
                text = f.read()
            if not text.strip():
                print("EMPTY translation")
                continue
        else:
            print(f"  [{i+1}/{len(pdf_files)}] {pdf_file}...", end=" ", flush=True)
            text = extract_text_from_pdf(pdf_path)
            if text.startswith("[ERROR"):
                print(f"FAILED: {text[:80]}")
                continue

        # Get base ID (without country prefix and .pdf)
        base_id = pdf_file.replace(f"{iso3}_", "").replace(".pdf", "")

        # Identify from content
        info = identify_legislation(text, pdf_file)

        # Enrich with known metadata
        meta = KEY_LEGISLATION_META.get(base_id, {})
        title = meta.get("title", info["first_lines"][:100])
        year = meta.get("year") or info["year"]
        last_amended = meta.get("last_amended") or info["last_amended"]
        category = meta.get("category", "unknown")

        record = {
            "iso3": iso3,
            "country": COUNTRIES[iso3],
            "filename": pdf_file,
            "base_id": base_id,
            "title": title,
            "year": year,
            "last_amended": last_amended,
            "category": category,
            "text_length": len(text),
            "text": text,
        }
        extracted.append(record)
        print(f"OK ({len(text):,} chars, {year or '?'})")

    print(f"\nSuccessfully extracted: {len(extracted)} documents")

    # Save extracted text CSV (without full text, too large)
    text_csv_path = os.path.join(OUTPUT_DIR, "legislation_extracted_metadata.csv")
    text_fields = ["iso3", "country", "filename", "base_id", "title", "year",
                    "last_amended", "category", "text_length"]
    with open(text_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=text_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(extracted)
    print(f"Metadata saved to: {text_csv_path}")

    # Step 2: Score each document
    print("\n--- Step 2: Scoring legislation ---")
    scored_docs = []

    for rec in extracted:
        text = rec["text"]
        scores = {}

        for dim_name, dim_config in DIMENSIONS.items():
            if dim_name == "legislative_currency":
                score = score_currency(rec["year"], rec["last_amended"])
                scores[dim_name] = score
                scores[f"{dim_name}_matches"] = 0
            else:
                score, n_matches, sample_matches = score_dimension(text, dim_config, dim_name)
                scores[dim_name] = score
                scores[f"{dim_name}_matches"] = n_matches

        # Total score
        total = sum(scores[d] for d in DIMENSIONS)
        scores["total_score"] = round(total, 1)

        scored_rec = {k: v for k, v in rec.items() if k != "text"}
        scored_rec.update(scores)
        scored_docs.append(scored_rec)

    # Step 3: Aggregate to country level
    print("\n--- Step 3: Aggregating to country level ---")
    country_scores = {}

    for iso3, country_name in sorted(COUNTRIES.items()):
        docs = [d for d in scored_docs if d["iso3"] == iso3]

        if not docs:
            print(f"  {country_name:25s} | NO LEGISLATION FOUND")
            country_scores[iso3] = {
                "iso3": iso3,
                "country": country_name,
                "n_documents": 0,
                "total_score": 0,
                "evidence_admissibility": 0,
                "penalty_framework": 0,
                "enforcement_authority": 0,
                "technology_provisions": 0,
                "liability_framework": 0,
                "legislative_currency": 0,
                "newest_year": None,
                "oldest_year": None,
                "primary_law_year": None,
                "key_laws": "",
            }
            continue

        # For country-level score: take BEST score per dimension across all docs
        # This makes sense because a country may have evidence provisions in one law
        # and technology mandates in another — they complement each other
        best_scores = {}
        for dim_name in DIMENSIONS:
            dim_scores = [d[dim_name] for d in docs]
            best_scores[dim_name] = max(dim_scores)

        total = sum(best_scores.values())

        # Metadata
        years = [d["year"] for d in docs if d.get("year")]
        primary_docs = [d for d in docs if d.get("category") == "primary_fisheries"]
        primary_year = primary_docs[0]["year"] if primary_docs and primary_docs[0].get("year") else None

        country_scores[iso3] = {
            "iso3": iso3,
            "country": country_name,
            "n_documents": len(docs),
            "total_score": round(total, 1),
            **best_scores,
            "newest_year": max(years) if years else None,
            "oldest_year": min(years) if years else None,
            "primary_law_year": primary_year,
            "key_laws": "; ".join(d["title"][:60] for d in docs[:3]),
        }

        print(f"  {country_name:25s} | {len(docs):2d} docs | Score: {total:5.1f}/100 | "
              f"Newest: {max(years) if years else '?'}")

    # Step 4: Save results
    print("\n--- Step 4: Saving results ---")

    # Document-level scores
    doc_csv_path = os.path.join(OUTPUT_DIR, "legislation_readiness_scores.csv")
    doc_fields = ["iso3", "country", "filename", "title", "year", "last_amended",
                   "category", "text_length", "total_score",
                   "evidence_admissibility", "penalty_framework",
                   "enforcement_authority", "technology_provisions",
                   "liability_framework", "legislative_currency"]
    with open(doc_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=doc_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(scored_docs)
    print(f"Document scores: {doc_csv_path}")

    # Country-level scores
    country_csv_path = os.path.join(RESULTS_DIR, "legislation_readiness_index.csv")
    country_fields = ["iso3", "country", "n_documents", "total_score",
                       "evidence_admissibility", "penalty_framework",
                       "enforcement_authority", "technology_provisions",
                       "liability_framework", "legislative_currency",
                       "newest_year", "oldest_year", "primary_law_year", "key_laws"]
    country_list = sorted(country_scores.values(), key=lambda x: x["total_score"], reverse=True)
    with open(country_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=country_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(country_list)
    print(f"Country index: {country_csv_path}")

    # Statistics JSON
    stats = {
        "n_countries": len([c for c in country_scores.values() if c["n_documents"] > 0]),
        "n_countries_missing": len([c for c in country_scores.values() if c["n_documents"] == 0]),
        "countries_missing": [c["country"] for c in country_scores.values() if c["n_documents"] == 0],
        "n_documents_total": len(scored_docs),
        "mean_country_score": round(
            sum(c["total_score"] for c in country_scores.values() if c["n_documents"] > 0) /
            max(1, len([c for c in country_scores.values() if c["n_documents"] > 0])), 1),
        "median_country_score": round(sorted(
            c["total_score"] for c in country_scores.values() if c["n_documents"] > 0
        )[len([c for c in country_scores.values() if c["n_documents"] > 0]) // 2], 1),
        "max_country_score": max(c["total_score"] for c in country_scores.values()),
        "min_country_score": min(c["total_score"] for c in country_scores.values() if c["n_documents"] > 0) if any(c["n_documents"] > 0 for c in country_scores.values()) else 0,
        "best_country": max(country_scores.values(), key=lambda x: x["total_score"])["country"],
        "worst_country_with_data": min(
            (c for c in country_scores.values() if c["n_documents"] > 0),
            key=lambda x: x["total_score"])["country"],
        "dimension_means": {},
        "countries_by_score": {c["country"]: c["total_score"] for c in country_list},
    }

    # Dimension means
    for dim_name in DIMENSIONS:
        vals = [c[dim_name] for c in country_scores.values() if c["n_documents"] > 0]
        stats["dimension_means"][dim_name] = round(sum(vals) / max(1, len(vals)), 1)

    stats_path = os.path.join(RESULTS_DIR, "manuscript_legislation_statistics.json")
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"Statistics: {stats_path}")

    # Final summary
    print(f"\n{'=' * 70}")
    print("LEGISLATION READINESS INDEX — COUNTRY RANKINGS")
    print(f"{'=' * 70}")
    print(f"{'Country':25s} | {'Score':>6s} | {'Evid':>5s} | {'Penal':>5s} | {'Enfor':>5s} | {'Tech':>5s} | {'Liab':>5s} | {'Curr':>5s} | {'Docs':>4s}")
    print("-" * 100)
    for c in country_list:
        print(f"  {c['country']:23s} | {c['total_score']:5.1f} | "
              f"{c['evidence_admissibility']:5.1f} | {c['penalty_framework']:5.1f} | "
              f"{c['enforcement_authority']:5.1f} | {c['technology_provisions']:5.1f} | "
              f"{c['liability_framework']:5.1f} | {c['legislative_currency']:5.1f} | "
              f"{c['n_documents']:4d}")

    print(f"\n{'=' * 70}")
    print(f"Mean score: {stats['mean_country_score']}/100")
    print(f"Best: {stats['best_country']} | Worst (with data): {stats['worst_country_with_data']}")
    if stats['countries_missing']:
        print(f"Missing: {', '.join(stats['countries_missing'])}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
