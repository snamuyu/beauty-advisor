# Beauty Advisor

AI 个人风格诊断 + 视频推荐后端（FastAPI + SQLite）。

## 目录结构

```
beauty-advisor/
├── main.py               # FastAPI 入口（/analyze、/history、/recommend）
├── config.py             # 配置（.env：百度/千问/数据库）
├── requirements.txt
├── load_env.bat          # Windows 加载环境变量
├── api/                  # 接口层
│   └── recommend.py      #   /recommend 推荐接口
├── core/                 # 业务核心
│   └── face_analyzer.py  #   百度人脸检测 + 四维计算
├── db/                   # 数据库层（Day 1）
│   ├── models.py         #   videos / user_profiles 模型
│   ├── session.py        #   引擎、会话、get_db、init_db
│   └── init_db.py        #   建表脚本
├── services/             # 服务层
│   ├── matching_engine.py#   Day 3 匹配逻辑
│   ├── ranking.py        #   Day 4 热度加权排序
│   └── rule_tagger.py    #   规则版视频标签提取
├── scripts/              # 数据/运维脚本
│   ├── import_data.py    #   Day 2 数据入库
│   ├── tag_videos.py     #   规则标签填充 videos.tags
│   └── fetch_heat.py     #   抓取 B 站真实热度
├── tests/                # 测试
│   ├── test_db.py
│   ├── test_recommend_api.py
│   └── test_api.py
├── legacy/               # 归档：未完成/未接入的旧代码（见 legacy/README.md）
├── data/                 # SQLite 数据库（beauty_advisor.db）
├── history/              # /analyze 产生的诊断记录 JSON
├── image/                # 测试图片
└── log/                  # 运行日志
```

## 快速开始

```bash
# 0. 进入项目专用虚拟环境（conda env: beauty-advisor）
conda activate beauty-advisor

python -m pip install -r requirements.txt

# 1. 建表（默认 SQLite: data/beauty_advisor.db）
python db/init_db.py

# 2. 数据入库（第二周融合 JSON → videos，history → user_profiles）
python scripts/import_data.py

# 3. 规则标签填充 + 抓取 B 站真实热度（可选）
python scripts/tag_videos.py
python scripts/fetch_heat.py

# 4. 启动 API（第四周起前端页面由 FastAPI 直接托管）
python -m uvicorn main:app --host 127.0.0.1 --port 8000
#    浏览器打开 http://127.0.0.1:8000 即可使用上传诊断 + 视频推荐页面
# 接口文档：http://127.0.0.1:8000/docs
```

## 接口

| 接口 | 方法 | 说明 |
| ---- | ---- | ---- |
| `/analyze` | POST | 上传 Base64 图片 → 风格诊断报告 |
| `/history` | GET | 历史诊断列表 |
| `/history/{record_id}` | GET | 单条诊断详情 |
| `/recommend` | POST | 接收用户画像 → Top N 视频推荐 |

## 推荐链路

`/recommend` → `services/matching_engine.py`（脸型/痛点/风格/关键词匹配）
+ `services/ranking.py`（点赞/收藏/播放热度加权）→ Top N 视频。

## 测试

```bash
python tests/test_db.py             # 数据库模型自测（内存库）
python tests/test_api.py            # /analyze 接口测试（需服务已启动）
python tests/test_recommend_api.py  # /recommend 接口测试（需服务已启动）
```

## 数据库切换 MySQL

设置环境变量 `DATABASE_URL`（需先建好数据库）：

```
mysql+pymysql://root:password@127.0.0.1:3306/beauty_advisor?charset=utf8mb4
```

然后重新执行 `python db/init_db.py` 即可。
