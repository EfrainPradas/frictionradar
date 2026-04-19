import json
with open("cli/results/ready_for_review_qa.json", "r") as f:
    review = json.load(f)

review.sort(key=lambda x: x.get("friction_score") or 0, reverse=True)

print("=== TOP 10 TIER 2 (inspect_human) ===")
for c in review[:10]:
    name = c.get("company_name", "?")
    fs = c.get("friction_score", 0)
    sig = c.get("signals_count", 0)
    pain = c.get("pain_clarity", "-")
    func = c.get("function_concentration", "-")
    qa = c.get("data_quality_status", "-")
    flags = c.get("qa_flags", [])
    rationale = c.get("tier_rationale", "")
    print(f"\n  {name}")
    print(f"    friction={fs}  signals={sig}  pain={pain}  func={func}  qa={qa}")
    print(f"    flags: {flags}")
    print(f"    rationale: {rationale[:100]}")

print("\n\n=== TIER 3 STATS ===")
with open("cli/results/needs_recollection_qa.json", "r") as f:
    recollect = json.load(f)

flag_count = {}
for c in recollect:
    for flag in c.get("qa_flags", []):
        flag_count[flag] = flag_count.get(flag, 0) + 1

for flag, count in sorted(flag_count.items(), key=lambda x: -x[1]):
    print(f"  {flag}: {count}")
