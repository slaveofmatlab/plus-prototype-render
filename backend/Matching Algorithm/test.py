from service import get_matcher

matcher = get_matcher()
results = matcher.query("五得利五星特精小麦粉25kg", top_n=5)

for r in results:
    print(f"{r['rank']}. {r['标准产品名称']}  编码:{r['标准产品编码']}  得分:{r['score']}")