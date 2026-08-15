# legacy（归档目录）

这里存放早期编写、但**未接入主流程 / 当前无法直接运行**的代码。
保留它们是为了不丢历史思路，不参与 `main.py` 的任何调用链。

## 文件说明

| 文件 | 原本用途 | 当前问题 |
| ---- | ---- | ---- |
| `llm_client.py` | 统一 LLM 客户端（本地/云端切换） | `config.LLM_CONFIG` 缺少 `provider` 键，import 即 KeyError |
| `style_analyzer.py` | 四维数据 → 风格分析（含规则降级） | 调用不存在的 `llm.chat_json()` |
| `video_tagger.py` | ASR 文本 → 视频人群标签 | 同上，且依赖 llm_client |
| `celery_app.py` | Celery 异步视频打标任务 | 依赖 video_tagger；未装 Redis 服务 |
| `test.py` | 早期调试脚本 | 依赖上述模块 |

> 注：当前项目用 `services/rule_tagger.py`（规则标签）替代了 `video_tagger.py`
> 的功能；`/recommend` 只依赖 `db/`、`services/` 和 `core/face_analyzer.py`，
> 不受本目录影响。

## 以后想复活这些代码

1. 在 `config.py` 的 `LLM_CONFIG` 里补上 `"provider": "cloud"`（或 `"local"`）。
2. 给 `legacy/llm_client.py` 的 `LLMClient` 增加 `chat_json(system_prompt, user_prompt, thinking=...)` 方法。
3. 把需要的文件移回 `core/`（并改回 `from core.llm_client import llm` 等引用），
   重跑测试确认无误后再接入。
