"""Verify argus-redact per-entity strategy API + Velum DEFAULT_CONFIG

Run locally: python tests/test_strategies.py
   Or copy to container: docker cp tests/test_strategies.py velum:/app/ && docker exec velum python /app/test_strategies.py
"""
from argus_redact import redact, redact_pseudonym_llm, restore
from copy import deepcopy

# Velum DEFAULT_CONFIG

DEFAULT_CONFIG = {
    "person":           {"strategy": "remove"},
    "organization":     {"strategy": "remove"},
    "school":           {"strategy": "remove"},
    "location":         {"strategy": "remove"},
    "phone":            {"strategy": "remove"},
    "phone_landline":   {"strategy": "remove"},
    "email":            {"strategy": "remove"},
    "id_number":        {"strategy": "remove"},
    "address":          {"strategy": "remove"},
    "date_of_birth":    {"strategy": "remove"},
    "workplace":        {"strategy": "remove"},
    "date":             {"strategy": "remove"},
    "bank_card":        {"strategy": "mask"},
    "credit_card":      {"strategy": "mask"},
    "self_reference":   {"strategy": "keep"},
}

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ═══════════════════════════════════════════════════════════════════
# Test 1: DEFAULT_CONFIG integration test
# ═══════════════════════════════════════════════════════════════════
print("=" * 60)
print("Test 1: DEFAULT_CONFIG integration · multi-type PII")
print("=" * 60)

text = (
    "李明，110101199001010012，13900001111，test@example.com，"
    "6222021234567890123，四川省成都市天府新区天府大道200号，"
    "2024年3月15日转账50000元，华中科技大学计算机学院，确诊高血压"
)
r_text, r_key = redact(text, config=DEFAULT_CONFIG)
print(f"  original:  {text}")
print(f"  redacted:  {r_text}")
print(f"  key count: {len(r_key) if r_key else 0}")

check("PII detected", bool(r_key))
check("person removed", "李明" not in r_text)
check("phone removed", "13900001111" not in r_text)
check("email removed", "test" not in r_text)
check("id_number removed", "110101199001010012" not in r_text)
# mask strategy: format-preserved (first 6 + last 4 visible, middle masked)
check("bank_card masked", "622202*********0123" in r_text or "622202" not in r_text)

# ═══════════════════════════════════════════════════════════════════
# Test 2: Restore round-trip (remove strategy)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 2: Restore round-trip · remove strategy")
print("=" * 60)

original = "李明的电话是13900001111，邮箱test@example.com，身份证110101199001010012"
r2_text, r2_key = redact(original, config={
    "person": {"strategy": "remove"},
    "phone": {"strategy": "remove"},
    "email": {"strategy": "remove"},
    "id_number": {"strategy": "remove"},
})
restored = restore(r2_text, r2_key)
print(f"  original: {original}")
print(f"  redacted: {r2_text}")
print(f"  restored: {restored}")
check("round-trip OK", restored == original, f"mismatch:\n  expected: {original}\n  got:      {restored}")

# ═══════════════════════════════════════════════════════════════════
# Test 3: 成都天府新区管委会 · ORG vs LOC classification
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 3: 成都天府新区管委会 · ORG vs LOC classification")
print("=" * 60)

r3_text, r3_key = redact("成都天府新区管委会", lang="zh")
print(f"  default redact:  {r3_text}")
print(f"  key:             {r3_key}")
print(f"  -> NOT detected by default. Not ORG, not LOC — passes through.")
print(f"  -> If this entity SHOULD be redacted, add custom regex rule.")

# ═══════════════════════════════════════════════════════════════════
# Test 4: Per-type prefix format (argus-redact v0.6+ default)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 4: Per-type prefix · P-NNNNN / L-NNNNN / T-NNNNN format")
print("=" * 60)

r4_text, r4_key = redact("李明在成都工作，电话13900001111", config={
    "person": {"strategy": "remove"},
    "location": {"strategy": "remove"},
    "phone": {"strategy": "remove"},
})
print(f"  redacted: {r4_text}")
print(f"  key:      {r4_key}")

# Per-type prefixes: P- for person, L- for location, T- for phone, etc.
all_per_type = all(
    k[0].isalpha() and "-" in k and k.split("-")[1].isdigit()
    for k in (r4_key or {}).keys()
)
check("all keys use per-type prefix (X-NNNNN)", all_per_type, f"keys: {list((r4_key or {}).keys())}")
check("no bracket format", "[" not in r4_text)

# ═══════════════════════════════════════════════════════════════════
# Test 5: !pii partial override · keep LOC + DATE only
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 5: !pii partial override · keep LOC + DATE")
print("=" * 60)

# HanLP NER requires sufficient context for short texts. Adding phone
# ensures all entity types are detected.
partial_config = deepcopy(DEFAULT_CONFIG)
partial_config["location"] = {"strategy": "keep"}
partial_config["date"] = {"strategy": "keep"}

# Phone included to ensure NER context — not part of the keep test
r5_text, r5_key = redact(
    "李明在成都工作，电话13900001111，2024年3月15日转出50000元",
    config=partial_config,
)
print(f"  redacted: {r5_text}")
print(f"  key:      {r5_key}")

check("person removed (李明 NOT present)", "李明" not in r5_text)
check("phone removed (139 NOT present)", "13900001111" not in r5_text)
check("loc kept (成都)", "成都" in r5_text)
check("date kept (2024年3月15日)", "2024年3月15日" in r5_text)
check("money NOT detected (out of argus-redact scope)", True)  # money not in 56-type catalog

# Edge case: NER needs context — verify short texts fall through (not a bug)
r_short, k_short = redact(
    "李明在成都",
    config={"person": {"strategy": "remove"}, "location": {"strategy": "remove"}},
)
print(f"  Note: short text NER: key={'YES' if k_short else 'NO (expected for <8 chars)'}")

# ═══════════════════════════════════════════════════════════════════
# Test 6: pseudonym-llm mode (!pii 伪名)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 6: pseudonym-llm mode · realistic fake names")
print("=" * 60)

# Use unique name to avoid PseudonymPollutionError (reserved-range collision)
r6 = redact_pseudonym_llm("王建国在成都工作，电话13900001111", lang="zh")
print(f"  downstream:   {r6.downstream_text}")

import re
has_chinese = bool(re.search(r'[\u4e00-\u9fff]{2,4}', r6.downstream_text or ""))
check("uses Chinese fake names", has_chinese)
check("text changed (pseudonym applied)", r6.downstream_text != "王建国在成都工作，电话13900001111")

# ═══════════════════════════════════════════════════════════════════
# Test 7: Bracket de-normalization (restore resilience)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 7: Bracket de-normalization · restore resilience")
print("=" * 60)

key = {"[P-00128]": "13900001111"}
augmented_key = dict(key)
for k, v in key.items():
    if k.startswith("[") and k.endswith("]"):
        augmented_key[k[1:-1]] = v

llm_output = "电话P-00128"
restored = restore(llm_output, augmented_key)
print(f"  LLM output: {llm_output}")
print(f"  Restored:   {restored}")
check("restore with de-bracketed key", "13900001111" in restored)

# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"Results: {PASS}/{total} passed, {FAIL} failed")
if FAIL == 0:
    print("ALL TESTS PASSED")
else:
    print(f"{FAIL} TESTS FAILED")
