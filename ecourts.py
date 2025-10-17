
import argparse
import requests
from bs4 import BeautifulSoup
import json
import os
import datetime
from urllib.parse import urljoin, urlencode
from typing import Optional, Dict, Any, List

BASE = "https://services.ecourts.gov.in/ecourtindia_v6/"
HEADERS = {
    "User-Agent": "ecourts-scraper/1.0 (+https://github.com/yourname/ecourts-scraper)"
}

def safe_get(url: str, params: dict = None, timeout: int = 15) -> Optional[requests.Response]:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"[ERROR] Request failed for {url} -> {e}")
        return None


def write_json(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON -> {path}")


def download_file(url: str, out_path: str) -> bool:
    r = safe_get(url)
    if not r:
        return False
    try:
        with open(out_path, "wb") as f:
            f.write(r.content)
        print(f"Downloaded -> {out_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save file: {e}")
        return False

def search_by_cnr(cnr: str) -> Dict[str, Any]:
    print(f"Searching for CNR: {cnr}")
    # Try direct query page
    params = {"cnr": cnr}
    # Attempt guess of JSON endpoint (may change) - this is a best-effort approach.
    json_guess = urljoin(BASE, "?p=casejson&cnr=")
    r = safe_get(urljoin(BASE, f"?p=casestatus%2Fcase_details&cnr={cnr}"))
    if r and r.headers.get("Content-Type", "").startswith("application/json"):
        try:
            return r.json()
        except Exception:
            pass

    r = safe_get(urljoin(BASE, f"?p=casestatus%2Findex&cnr={cnr}"))
    result = {"cnr": cnr, "found": False, "raw": None}
    if not r:
        return result
    html = r.text
    result["raw"] = html[:5000] 

    soup = BeautifulSoup(html, "html.parser")
    info = {}
    title = soup.find(lambda t: t.name in ["h1", "h2", "h3"] and "CNR" in t.text)
    if title:
        info["title"] = title.text.strip()

    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            pdf_links.append(urljoin(BASE, href))
    if pdf_links:
        info["pdf_links"] = pdf_links

    texts = soup.get_text(separator="|", strip=True)
    if "cause list" in texts.lower() or "listed" in texts.lower():
        info["page_mentions_listing"] = True

    result.update({"found": True, "info": info})
    return result


def search_by_case(case_type: str, number: str, year: str) -> Dict[str, Any]:
    """Search by case type/number/year. This will attempt case-status search form.
    """
    print(f"Searching for case: {case_type} {number}/{year}")
    params = {
        "case_type": case_type,
        "case_no": number,
        "case_year": year
    }

    r = safe_get(urljoin(BASE, "?p=casestatus%2Findex"), params=params)
    if not r:
        return {"found": False}
    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if case_type.lower() in text.lower() or number in text or year in text:
            results.append({"text": text, "href": urljoin(BASE, href)})
    return {"found": bool(results), "results": results}


def get_cause_list_for_court(state: str = None, district: str = None, court_complex: str = None, date: datetime.date = None) -> Dict[str, Any]:
 
    date = date or datetime.date.today()
    print(f"Attempting to fetch cause list for {date.isoformat()} (may require captcha).")
    r = safe_get(urljoin(BASE, "?p=cause_list%2Findex"))
    if not r:
        return {"ok": False, "reason": "Failed to load cause list index"}
    soup = BeautifulSoup(r.text, "html.parser")

    pdfs = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower() and "cause" in href.lower():
            pdfs.append(urljoin(BASE, href))
    if pdfs:
        return {"ok": True, "pdfs": pdfs}
    return {"ok": False, "reason": "No direct cause-list PDFs found (captcha likely required)"}


def check_listing_in_causelist(causelist_html: str, case_identifiers: Dict[str, str]) -> Optional[Dict[str, str]]:
    
    soup = BeautifulSoup(causelist_html, "html.parser")
    text = soup.get_text(separator="|", strip=True).lower()

    if "cnr" in case_identifiers and case_identifiers["cnr"]:
        cnr = case_identifiers["cnr"].lower()
        if cnr in text:

            for line in text.split("|"):
                if cnr in line:
                    tokens = line.split()
                    serial = None
                    court = None
                   
                    for tok in tokens:
                        if tok.isdigit():
                            serial = tok
                            break
                    return {"serial": serial or "?", "court": court or "?", "line": line}

    if "number" in case_identifiers and "year" in case_identifiers:
        needle = f"{case_identifiers['number']}/{case_identifiers['year']}"
        if needle.lower() in text:
            for line in text.split("|"):
                if needle.lower() in line:
                    tokens = line.split()
                    serial = next((t for t in tokens if t.isdigit()), None)
                    return {"serial": serial or "?", "court": "?", "line": line}
    return None


def main():
    parser = argparse.ArgumentParser(description="eCourts Scraper - Intern Task implementation")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cnr", help="CNR number (16 chars)")
    group.add_argument("--case", nargs=3, metavar=("CASE_TYPE", "NUMBER", "YEAR"), help="Case search: TYPE NUMBER YEAR")
    parser.add_argument("--today", action="store_true", help="Check listing for today")
    parser.add_argument("--tomorrow", action="store_true", help="Check listing for tomorrow")
    parser.add_argument("--causelist", action="store_true", help="Download entire cause list for today (best-effort)")
    parser.add_argument("--download-pdf", action="store_true", help="If case PDF found, try to download it")
    parser.add_argument("--out", default="results.json", help="Output JSON file path")

    args = parser.parse_args()

    output = {"query": {}, "results": None}

    if args.cnr:
        output["query"]["cnr"] = args.cnr
        res = search_by_cnr(args.cnr)
        output["results"] = res
       
        if args.today or args.tomorrow:
            date = datetime.date.today() if args.today else datetime.date.today() + datetime.timedelta(days=1)
            cl = get_cause_list_for_court(date=date)
            output["cause_list_attempt"] = cl
            if cl.get("ok") and cl.get("pdfs"):
                # download first pdf and scan
                pdf_url = cl["pdfs"][0]
                r = safe_get(pdf_url)
                if r:
                    found = check_listing_in_causelist(r.text, {"cnr": args.cnr})
                    output["found_in_causelist"] = found
     
        if args.download_pdf and res.get("info") and res["info"].get("pdf_links"):
            os.makedirs("downloads", exist_ok=True)
            for i, pdf in enumerate(res["info"]["pdf_links"]):
                fname = os.path.join("downloads", f"{args.cnr}_doc_{i+1}.pdf")
                download_file(pdf, fname)

    elif args.case:
        case_type, number, year = args.case
        output["query"]["case_type"] = case_type
        output["query"]["number"] = number
        output["query"]["year"] = year
        res = search_by_case(case_type, number, year)
        output["results"] = res
        if args.today or args.tomorrow:
            date = datetime.date.today() if args.today else datetime.date.today() + datetime.timedelta(days=1)
            cl = get_cause_list_for_court(date=date)
            output["cause_list_attempt"] = cl
            if cl.get("ok") and cl.get("pdfs"):
                pdf_url = cl["pdfs"][0]
                r = safe_get(pdf_url)
                if r:
                    found = check_listing_in_causelist(r.text, {"number": number, "year": year})
                    output["found_in_causelist"] = found

    if args.causelist:
        cl = get_cause_list_for_court(date=datetime.date.today())
        output.setdefault("extras", {})["cause_list"] = cl
        # If PDF(s) found, download them
        if cl.get("ok") and cl.get("pdfs"):
            os.makedirs("cause_lists", exist_ok=True)
            for i, pdf in enumerate(cl["pdfs"]):
                outp = os.path.join("cause_lists", f"cause_list_{i+1}.pdf")
                download_file(pdf, outp)


    write_json(args.out, output)
    print("Done.")


if __name__ == "__main__":
    main()
