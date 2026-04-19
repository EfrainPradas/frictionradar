import urllib3, requests, json, os

urllib3.disable_warnings()

r = requests.get(
    "https://nike.com/careers", headers={"User-Agent": "Test"}, verify=False, timeout=15
)
text_lower = r.text.lower()

results = []

CAT_KW = {
    "retail": ["retail", "store"],
    "distribution": ["distribution", "warehouse"],
    "technology": ["technology", "tech"],
    "manufacturing": ["manufacturing"],
}

for cat, keywords in CAT_KW.items():
    for kw in keywords:
        if kw in text_lower:
            results.append(f"{cat}")
            break

output = {"found": results, "count": len(results), "status": r.status_code}

with open("C:/Ubuntu/home/efraiprada/frictionradar/test_output.json", "w") as f:
    json.dump(output, f)

print(f"Done. Found {len(results)} categories: {results[:5]}")
