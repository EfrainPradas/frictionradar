#!/usr/bin/env python
import sys, urllib3, re

sys.path.insert(0, ".")
urllib3.disable_warnings()

from app.collectors.dynamic_careers import DynamicCareersCollector


class MockComp:
    domain = "nike.com"


collector = DynamicCareersCollector()

# Test each method
print("=== Testing _extract_with_requests ===")
result = collector._extract_with_requests("nike.com")
print(f"Result: {result}")

if result:
    print("=== Found data, testing _find_categories ===")
    # Test finding categories
    import requests

    r = requests.get(
        "https://nike.com/careers",
        headers={"User-Agent": "Test"},
        verify=False,
        timeout=15,
    )
    text_lower = r.text.lower()

    found = []
    for cat, keywords in collector.CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found.append(cat)
                print(f"  FOUND: {cat} (keyword: {kw})")
                break

    print(f"\nTotal categories found: {len(found)}")
    print(f"Categories: {found[:5]}")
else:
    print("ERROR: No data returned!")
