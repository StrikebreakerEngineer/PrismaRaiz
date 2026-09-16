import json
import subprocess

from bs4 import BeautifulSoup

# Must include the 'dle.' subdomain
BASE_HOST = "https://dle.rae.es"
AUTH_HEADER = "Basic cDY4MkpnaFMzOmFHRlVkQ2lFNDM0"

def curl_get(url):
    """Uses system curl with redirect following and browser headers."""
    cmd = [
        "curl", "-s", "-L",  # -L follows redirects automatically
        "-H", f"Authorization: {AUTH_HEADER}",
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "-H", "Accept: application/json, text/plain, */*",
        "-H", "Accept-Language: es-ES,es;q=0.9",
        "--compressed",
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"Curl process error: {result.stderr}")
        return None
    return result.stdout

def get_definition(word):
    clean_word = word.strip()
    
    # 1. Query the search endpoint
    search_url = f"{BASE_HOST}/data/search?w={clean_word}"
    print(f"Searching: {search_url}")
    search_raw = curl_get(search_url)
    
    if not search_raw:
        return None
        
    try:
        search_json = json.loads(search_raw)
    except json.JSONDecodeError:
        print("Failed to decode JSON. Server response:")
        print(search_raw[:300])
        return None
        
    results = search_json.get("res", [])
    if not results:
        print(f"Word '{clean_word}' not found.")
        return None
        
    # Get the ID of the first match
    first_match = results[0]
    word_id = first_match["id"]
    header = first_match.get("header", clean_word)
    print(f"Found: '{header}' (ID: {word_id})")
    
    # 2. Fetch the entry HTML
    fetch_url = f"{BASE_HOST}/data/fetch?id={word_id}"
    print(f"Fetching definition: {fetch_url}")
    html_content = curl_get(fetch_url)
    
    if not html_content:
        return None
        
    # 3. Parse definitions with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    definitions = []
    
    for p in soup.find_all("p", class_=lambda c: c and any(cls in c for cls in ["j", "n_ace"])):
        definitions.append(p.get_text(" ", strip=True))
        
    return definitions

if __name__ == "__main__":
    definitions = get_definition("ser")
    if definitions:
        print(f"\n--- Definitions Found ({len(definitions)}) ---")
        for idx, item in enumerate(definitions, 1):
            print(f"{idx}. {item}")