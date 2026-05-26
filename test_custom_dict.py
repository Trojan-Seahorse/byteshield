"""Test argus-redact `names` parameter for compound location injection.

验证 argus-redact 的 `names` 参数能否用于注入非标准行政后缀的经济功能区地名。

Run in Docker: docker exec velum python /app/test_custom_dict.py
"""

from argus_redact import redact, restore

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
# Test 1: names 参数基本行为——能否强制脱敏指定字符串
# ═══════════════════════════════════════════════════════════════════
print("=" * 60)
print("Test 1: names 参数 · 强制脱敏复合地名")
print("=" * 60)

compound_locations = [
    "成都天府新区",
    "雄安新区",
    "浦东新区",
    "中关村科技园",
]

for loc in compound_locations:
    r, k = redact(f"我在{loc}工作", names=[loc], lang="zh")
    detected = bool(k) and loc not in r
    replaced_text = r if detected else "(not detected)"
    print(f"  {loc}: detected={detected}  redacted={replaced_text}")
    check(f"names 参数检测到 {loc}", detected)

# ═══════════════════════════════════════════════════════════════════
# Test 2: 子串匹配——names 中的地名能否在更长文本中被检测
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 2: 子串匹配 · 机构名嵌入场景")
print("=" * 60)

test_cases = [
    ("成都天府新区区管委会", "成都天府新区区"),
    ("雄安新区党工委", "雄安新区"),
    ("浦东新区人民政府", "浦东新区"),
    ("中关村科技园管委会", "中关村科技园"),
]

for text, name in test_cases:
    r, k = redact(text, names=[name], lang="zh")
    name_detected = name not in r
    print(f"  '{text}' → names=['{name}']: detected={name_detected}")
    if name_detected:
        print(f"    redacted: {r}")
    check(f"子串匹配: {name} in {text}", name_detected)

# ═══════════════════════════════════════════════════════════════════
# Test 3: 实体类型——names 参数脱敏的实体被归类为什么类型
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 3: 实体类型分类 · names 参数的类型映射")
print("=" * 60)

r, k, details = redact("成都天府新区区管委会", names=["成都天府新区区"], lang="zh", detailed=True)
entities = details.get("entities", [])
for e in entities:
    print(f"  entity: {e['original']} → {e['replacement']}  type={e['type']}  layer={e['layer']}")

# names 参数实体被归为什么类型？仅做记录——不影响功能（per-type 前缀已区分类型）
name_type = entities[0]["type"] if entities else "unknown"
print(f"  names 参数实体类型 = {name_type}（argus-redact 默认 per-type 前缀，格式 X-NNNNN）")
check("names 参数实体被检测到", len(entities) > 0)

# ═══════════════════════════════════════════════════════════════════
# Test 4: names + config 组合——能否用 location: remove 策略控制
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 4: names + config 策略控制")
print("=" * 60)

r, k = redact(
    "成都天府新区区管委会和雄安新区党工委开会",
    names=["成都天府新区区", "雄安新区"],
    config={"location": {"strategy": "remove"}},
    lang="zh",
)
print(f"  redacted: {r}")
print(f"  key:      {k}")

both_removed = "成都天府新区区" not in r and "雄安新区" not in r
per_type_prefix_ok = all(k[0].isalpha() and "-" in k and k.split("-")[1].isdigit() for k in (k or {}).keys())
check("两个地名都被脱敏", both_removed)
check("使用 per-type 前缀 (X-NNNNN)", per_type_prefix_ok)

# ═══════════════════════════════════════════════════════════════════
# Test 5: 标准行政地名基准——确认现有 NER 覆盖
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 5: 标准行政地名基准 · NER 覆盖确认")
print("=" * 60)

standard_cases = [
    "北京大学",       # 北京 = known city, 大学 = center word
    "海淀区卫健委",   # 海淀区 = known district, 卫健委 = center word
    "江苏省人民医院", # 江苏省 = known province
]

for text in standard_cases:
    r, k = redact(text, config={"location": {"strategy": "remove"}}, lang="zh")
    detected = bool(k)
    print(f"  '{text}': detected={detected}  redacted={r if detected else '(pass-through)'}")
    check(f"NER 检测到标准地名在 {text} 中", detected, f"redacted={r}")

# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"Results: {PASS}/{total} passed, {FAIL} failed")
if FAIL == 0:
    print("ALL TESTS PASSED — names 参数方案可行")
else:
    print(f"{FAIL} TESTS FAILED — 需进一步分析失败原因")
