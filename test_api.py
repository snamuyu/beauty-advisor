import requests
import base64
import json

# 读取图片并转成 Base64
with open("./image/test.jpg", "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode()

# 发送请求
response = requests.post(
    "http://127.0.0.1:8000/analyze",
    json={"image_base64": image_base64}
)

# 打印结果
if response.status_code == 200:
    result = response.json()
    
    print("=" * 50)
    print(f"🎨 风格标签：{result['style_tag']}")
    print(f"📌 关键词：{', '.join(result['keywords'])}")
    print(f"🌟 明星参考：{', '.join(result['celebrity_refs'])}")
    print("=" * 50)
    
    print(f"\n💡 定位分析：\n{result['positioning_reason']}")
    
    print(f"\n{'=' * 50}")
    print("💄 妆容建议：")
    for item in result['makeup_advice']:
        print(f"\n  【{item['area']}】")
        print(f"  执行：{item['action']}")
        print(f"  理由：{item['reason']}")
    
    print(f"\n{'=' * 50}")
    print("💇 发型建议：")
    print(f"  长度：{result['hair_advice']['length']}")
    print(f"  卷度：{result['hair_advice']['curl']}")
    print(f"  刘海：{result['hair_advice']['bangs']}")
    
    print(f"\n{'=' * 50}")
    print(f"✨ 总结：{result['summary']}")
    
else:
    print("请求失败：", response.status_code, response.text)