import sys
import urllib3
import requests
import re

urllib3.disable_warnings()

r = requests.get(
    "https://nike.com/careers",
    verify=False,
    timeout=15,
    headers={"User-Agent": "Mozilla/5.0"},
)
text = r.text

m = re.search(r"(\d+)\s*open\s*positions?", text, re.I)
print(f"MATCH: {m.group() if m else 'None'}", file=sys.stderr)
sys.stderr.flush()

counts = re.findall(r"\b(\d{2,4})\b", text)
unique = sorted(set(counts), key=lambda x: int(x))[-10:]
print(f"COUNTS: {unique}", file=sys.stderr)
