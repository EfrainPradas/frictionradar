"""Generate a re-collection input JSON from the needs_recollection results.

This creates a filtered input file with only the companies that need
re-collection, preserving their metadata from the previous run.
"""
import json
from pathlib import Path

results_dir = Path("C:/Ubuntu/home/efraiprada/frictionradar/cli/results")
output_file = results_dir / "recollection_input.json"

# Load all results to find companies that need re-collection
all_results = json.loads((results_dir / "all_results.json").read_text(encoding="utf-8"))
needs = [r for r in all_results if r.get("status") == "needs_recollection"]

# Also include companies with very low extraction coverage from ready_for_review
# (they have some signals but not enough depth)
ready = [r for r in all_results if r.get("status") == "ready_for_review"
         and r.get("extraction_coverage") == "low"]

# Build input entries
entries = []
for r in needs + ready:
    entry = {
        "company_name": r["company_name"],
        "domain": r["domain"],
    }
    if r.get("industry"):
        entry["industry"] = r["industry"]
    if r.get("location"):
        entry["location"] = r["location"]
    if r.get("source"):
        entry["source"] = r["source"]
    entries.append(entry)

# Remove duplicates by domain
seen = set()
deduped = []
for e in entries:
    if e["domain"] not in seen:
        seen.add(e["domain"])
        deduped.append(e)

output_file.write_text(json.dumps(deduped, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Generated {len(deduped)} companies for re-collection")
print(f"  from needs_recollection: {len(needs)}")
print(f"  from ready_for_review (low coverage): {len(ready)}")
print(f"  after dedup: {len(deduped)}")
print(f"Output: {output_file}")
