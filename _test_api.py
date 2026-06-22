"""Test what the API actually returns for 缺失后果"""
import json, urllib.request, time

# Wait for server
for i in range(5):
    try:
        urllib.request.urlopen("http://localhost:8001/api/health", timeout=5)
        break
    except:
        time.sleep(2)

# Trigger analysis
req = urllib.request.Request(
    "http://localhost:8001/api/tax-risk-docs/analyze?company_id=1",
    method="POST"
)
resp = urllib.request.urlopen(req, timeout=180)
data = json.loads(resp.read())

report = data.get('report', {})
all_findings = report.get('all_findings', [])

print("=== 资料完备度综合评估 items ===")
for f in all_findings:
    if '资料完备度综合评估' == f.get('type', ''):
        for item in f.get('items', []):
            name = item.get('缺失资料', '?')
            consequence = item.get('缺失后果', '?')
            print(f"  [{name}] {consequence[:120]}")
        break
else:
    print("NOT FOUND: 资料完备度综合评估")

print()
print("=== 记账凭证缺失 (individual finding) ===")
for f in all_findings:
    if '记账凭证缺失' == f.get('type', ''):
        print(f"  detail: {f.get('detail','?')[:120]}")
        print(f"  description: {f.get('description','?')[:120]}")
        print(f"  tax_impact: {f.get('tax_impact','?')[:120]}")
        break
else:
    print("NOT FOUND: 记账凭证缺失")
