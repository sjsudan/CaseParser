#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Causelist → File No. matcher (Algorithm v2.2b.a)

This script automates the retrieval of internal 'File Numbers' for court cases 
listed in a daily 'Causelist' PDF. It works by:
1. Loading a Master Database (Excel/CSV) of all internal cases.
2. Parsing the PDF Causelist to extract Case Numbers and Party Names using Regex.
3. Normalizing case numbers (e.g., turning '1/2023' into '01/23').
4. Matching the PDF data against the Master DB using a waterfall algorithm 
   (Exact Match -> Cross-Type Token Match -> Title Overlap).
"""

import argparse
import re
from pathlib import Path
import pandas as pd
import pdfplumber

# ==========================================
# SECTION 1: DATA NORMALIZERS
# ==========================================
# These functions standardize input strings to ensure "W.P. (C) 1/2022" 
# matches "WPC 01/22" in the database.

def norm_case_type(s: str) -> str:
    """
    Standardizes case type abbreviations.
    Example: 'W.P.(C)' -> 'WPC', 'OW P' -> 'OWP'.
    """
    if pd.isna(s): return ""
    s = str(s).upper().strip()
    # Remove dots, spaces, parens to create a raw signature
    s = re.sub(r"[.\s()]", "", s)
    # Manual corrections for common typo patterns
    s = s.replace("WP C","WPC").replace("WP(C)","WPC").replace("OW P","OWP").replace("C P OWP","CPOWP")
    return s

def norm_year(token: str) -> str:
    """
    Standardizes case numbers to 'NN/YY' format.
    - Pads numbers: '1/22' -> '01/22'
    - Truncates years: '/2023' -> '/23' (keeps /2000 as is)
    """
    if pd.isna(token): return ""
    token = str(token).upper().strip()
    
    # Regex checks for "Number / Year" pattern
    m = re.match(r"^(\d+)\s*/\s*(\d{2,4})$", token)
    if not m:
        return token # Return raw if it doesn't look like a case number
        
    num, year = m.groups()
    
    # Step 1: Pad the case number to at least 2 digits (e.g. 5 -> 05)
    try:
        num_int = int(num)
        num_norm = f"{num_int:02d}"
    except:
        num_norm = num
        
    # Step 2: Normalize year to 2 digits, unless it's exactly "2000"
    if len(year) == 4 and year != "2000":
        year_norm = year[-2:]
    else:
        year_norm = year
        
    return f"{num_norm}/{year_norm}"

def clean_title_for_match(t: str) -> str:
    """
    Removes legal jargon from party names to improve fuzzy matching.
    Input: "Rahul Gupta And Others" -> Output: "RAHUL GUPTA"
    """
    if pd.isna(t): return ""
    t = str(t).upper()
    # Remove 'vs', 'others', 'another'
    t = re.sub(r"\bAND\s+OTHERS?\b", " ", t)
    t = re.sub(r"\bAND\s+ANR\.?\b", " ", t)
    # Remove punctuation
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def is_party_like(line: str) -> bool:
    """
    Heuristic to check if a text line contains a Party Name.
    Returns True if line contains 'VS', specific keywords (STATE, BANK), 
    or at least two capitalized words.
    """
    if not line: return False
    u = line.upper()
    if re.search(r"\b(VS| V |VERSUS)\b", u): return True
    # Keywords common in institutional litigants
    if re.search(r"\b(STATE|UNION|CENTRAL|DISTRICT|TEHSILDAR|TALUKA|SDM|DC|DM|REVENUE|BANK|CORPORATION|DEPARTMENT|COMMISSIONER|AUTHORITY)\b", u):
        return True
    # Fallback: Does it look like a name (Two or more capitalized words)?
    toks = re.findall(r"\b[A-Z][A-Z]+\b", u)
    return len(toks) >= 2

def cleanse_noise(line: str) -> bool:
    """
    Identifies "noise" lines in the PDF (Lawyer names, Application IDs) 
    that should NOT be treated as Party Names.
    """
    u = (line or "").upper()
    # Check for lawyer prefixes (Adv, AAG) or Application types (CM, IA, CRM)
    return bool(re.search(r"\b(FOR\s+(PET|RES|APPLICANT|RESPONDENT)|CAVEAT|AAG\b|SR\.?\s*ADV|ADV\.)\b", u) or
                re.match(r"^\s*(CM|IA|CRM|CRLM|CRR|CRMC|CMM|CAVT|CAVEAT)\b", u))

# ==========================================
# SECTION 2: DATA LOADING
# ==========================================

def load_master(master_path: Path) -> pd.DataFrame:
    """
    Loads the Master Database. Supports both .xlsx (multi-sheet) and .csv.
    Applies normalization immediately upon loading.
    """
    if master_path.suffix.lower() in (".xlsx", ".xls"):
        xls = pd.ExcelFile(master_path)
        frames = []
        for sheet in xls.sheet_names:
            df = xls.parse(sheet)
            df["__sheet__"] = sheet
            frames.append(df)
        master = pd.concat(frames, ignore_index=True)
    else:
        master = pd.read_csv(master_path)
        if "__sheet__" not in master.columns:
            master["__sheet__"] = ""
            
    # Apply normalizers to Master Data columns
    master["case_type_norm"] = master["Case Type"].map(norm_case_type)
    master["case_no_norm"] = master["Case No."].map(norm_year)
    master["title_clean"] = master["Title"].map(clean_title_for_match)
    return master

def index_master(master: pd.DataFrame):
    """
    Creates lookup dictionaries (Hash Maps) for O(1) matching speed.
    1. by_ct_cno: Key = (CaseType, CaseNo) -> Returns exact record
    2. by_cno:    Key = CaseNo -> Returns list of records (for cross-type matching)
    """
    by_ct_cno = {}
    by_cno = {}
    for _, r in master.iterrows():
        key = (str(r["case_type_norm"]), str(r["case_no_norm"]))
        if key not in by_ct_cno:
            by_ct_cno[key] = r
        if pd.notna(r["case_no_norm"]) and str(r["case_no_norm"]):
            by_cno.setdefault(str(r["case_no_norm"]), []).append(r)
    return by_ct_cno, by_cno

def read_pdf_lines(pdf_path: Path):
    """Extracts raw text from PDF pages and splits into lines."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return [l for l in text.splitlines() if l.strip()]

def write_excel(df: pd.DataFrame, out_path: Path):
    """Writes results to Excel with auto-adjusted column widths."""
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Causelist")
        ws = writer.sheets["Causelist"]
        for i, col in enumerate(df.columns):
            # Calculate max width based on content length
            width = min(72, max(12, int(df[col].astype(str).map(len).max() + 2)))
            ws.set_column(i, i, width)

# ==========================================
# SECTION 3: PDF PARSER
# ==========================================

def parse_blocks(lines):
    """
    Scans PDF text to identify Case Blocks.
    Logic:
    1. Finds a line starting with a Serial No (e.g. "101 WP(C) 12/2023").
    2. Captures following lines as part of the block until the next Serial No is found.
    3. Extracts 'Clubbed Cases' (c/w) hidden inside the block text.
    """
    # Regex for the start of a new case entry: "101  CaseType  CaseNo  Title"
    start_pat = re.compile(r"^\s*(\d+)\s+([A-Za-z()\.]+)\s+([A-Za-z0-9\-()/ ]+/\d{2,4})\s*(.*)$", re.I)
    
    # Regex for "Clubbed with" cases inside the text block
    cw_inline_pat = re.compile(r"(?:\bc/w\b|\bwith\b)\s*(?:(?P<ctype>[A-Za-z()\.]+)\s+)?(?P<cno>[A-Za-z0-9\-() ]+/\d{2,4})(?:\s+(?P<title>[^\n]+))?", re.I)
    
    rows = []
    i = 0
    while i < len(lines):
        m = start_pat.match(lines[i])
        if not m:
            i += 1; continue
            
        # Extract main case details
        sno, ctype_raw, cno_raw, rest = m.groups()
        ctype = norm_case_type(ctype_raw)
        cno = norm_year(cno_raw)
        
        # Title Extraction Logic
        header_tail = (rest or "").strip()
        title_parts = []
        if header_tail:
            title_parts.append(header_tail)
            title_src = "Inline title"
        else:
            title_src = ""
            
        # Scan forward to collect multi-line titles/details
        j = i + 1
        block = [lines[i]]
        while j < len(lines) and not start_pat.match(lines[j]):
            ln = lines[j]
            block.append(ln)
            # Heuristic: If it looks like a party name and not lawyer noise, add to title
            if not cleanse_noise(ln) and is_party_like(ln) and len(title_parts) < 2:
                title_parts.append(ln.strip())
                title_src = (title_src or "Next-line party")
            j += 1
        i = j # Move pointer
        
        title = re.sub(r"\s+", " ", " ".join(title_parts).strip())
        rows.append({"S.No": sno, "Case Type": ctype, "Case No.": cno, "Title": title, "_TitleSrc": title_src or "Inline only"})
        
        # Check for clubbed cases in the collected block
        block_text = "\n".join(block)
        for mm in cw_inline_pat.finditer(block_text):
            ct2 = norm_case_type(mm.group("ctype") or ctype) # Inherit case type if missing
            cn2 = norm_year(mm.group("cno"))
            t2 = (mm.group("title") or "").strip()
            rows.append({"S.No": sno, "Case Type": ct2, "Case No.": cn2, "Title": t2, "_TitleSrc": "Clubbed inline"})
            
    return pd.DataFrame(rows)

# ==========================================
# SECTION 4: MATCH ENGINE
# ==========================================

def match_engine(row, by_ct_cno, by_cno):
    """
    The Waterfall Matching Algorithm:
    1. Try Exact Match: (CaseType + CaseNo) matches exactly.
    2. Try Cross-Type Match: If CaseNo matches but CaseType differs (e.g. WP(C) vs OWP),
       check if the first word of the Party Name matches.
    3. Try Title Overlap: If CaseNo matches, check for any significant word overlap in Title.
    """
    ct, cno, title = row["Case Type"], row["Case No."], row.get("Title","")
    
    # Priority 1: Exact Match
    rec = by_ct_cno.get((ct, cno))
    if rec is not None:
        fno = rec["File No."]
        verb = f'{fno} {rec["Case Type"]} {rec["Case No."]} {rec.get("Title","")}'
        return fno, verb, "Exact (type+no)"
        
    # Priority 2: Fuzzy Logic on Candidates with same Case Number
    cands = by_cno.get(cno, [])
    if cands and title:
        tq_list = clean_title_for_match(title).split()
        first_token = tq_list[0] if tq_list else ""
        
        best, bestscore = None, -1
        for cand in cands:
            cand_tokens = str(cand.get("title_clean","")).split()
            
            # Check First Token (High Confidence)
            if cand_tokens and first_token and cand_tokens[0] == first_token:
                fno = cand["File No."]
                verb = f'{fno} {cand["Case Type"]} {cand["Case No."]} {cand.get("Title","")}'
                return fno, verb, "Cross-type first-token match"
                
            # Check General Overlap (Lower Confidence)
            score = len(set(tq_list) & set(cand_tokens))
            if score > bestscore: 
                best, bestscore = cand, score
                
        if best is not None and bestscore >= 1:
            fno = best["File No."]
            verb = f'{fno} {best["Case Type"]} {best["Case No."]} {best.get("Title","")}'
            return fno, verb, "Cross-type title overlap"
            
        return "", "", "No overlap (type mismatch)"
        
    return "", "", "Not found"

# ==========================================
# SECTION 5: RUNNER
# ==========================================

def run(master_path: Path, query_pdf: Path, out_path: Path, mode: str):
    print(f"Loading master: {master_path}...")
    master = load_master(master_path)
    by_ct_cno, by_cno = index_master(master)
    
    print(f"Parsing PDF: {query_pdf}...")
    lines = read_pdf_lines(query_pdf)
    df = parse_blocks(lines)
    print(f"Found {len(df)} cases (including clubbed). Matching...")

    out_rows = []
    for _, r in df.iterrows():
        fno, verb, chk = match_engine(r, by_ct_cno, by_cno)
        out_rows.append({
            "S.No": r["S.No"],
            "Case Type": r["Case Type"],
            "Case No.": r["Case No."],
            "Title": r.get("Title",""),
            "File No.": fno,
            "Matched (from master)": verb,
            "Check": chk
        })
    out_df = pd.DataFrame(out_rows)
    
    # Filter output if 'cleaned' mode is selected
    if mode.lower() == "cleaned":
        mask = ~out_df["Check"].str.contains("Not found|No overlap", case=False, na=False)
        out_df = out_df[mask].copy()

    write_excel(out_df, out_path)
    return out_df

def main():
    ap = argparse.ArgumentParser(description="LegalParser: Match PDF Causelist against Internal Master DB")
    ap.add_argument("--master", required=True, help="Path to Master Excel/CSV")
    ap.add_argument("--query", required=True, help="Path to Causelist PDF")
    ap.add_argument("--out", required=True, help="Path for Output Excel")
    ap.add_argument("--mode", default="cleaned", choices=["cleaned","full"], help="Output mode (cleaned=only matches, full=all rows)")
    args = ap.parse_args()
    
    run(Path(args.master), Path(args.query), Path(args.out), args.mode)
    print(f"Done! Results saved to: {args.out}")

if __name__ == "__main__":
    main()