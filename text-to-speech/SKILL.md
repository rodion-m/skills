---
name: text-to-speech
description: 文本转语音工具 - 默认 MiniMax TTS，支持切换 Edge TTS 和 Kokoro TTS (v1.1-zh)
version: 3.5.0
changelog:
  - 2026-08-01: v3.5.0 新增 MiniMax 词级时间戳 sidecar；只保存校验后的时间段，不保存短期签名下载 URL；Edge/Kokoro 显式拒绝该参数
  - 2026-08-01: v3.4.0 新增 MiniMax 声音克隆上传/创建/激活费用门禁、本机 0600 克隆音色档，以及整期固定 commercial_narration 表达档；克隆音色或表达档变化会使下游缓存失效
  - 2026-07-18: v3.3.1 MiniMax 语境适配移除逐 beat emotion 注入，避免同一场景语气跳变；保留 speed/volume/pitch 轻量调整并同步测试文档
  - 2026-07-18: v3.3.0 MiniMax 默认音色改为 Chinese (Mandarin)_Reliable_Executive；新增 MiniMax 专属语境适配层，按开场、总结、解释、步骤、提醒、资源、结论和关注引导自动微调表达；Edge/Kokoro 行为不变
  - 2026-07-17: v3.2.0 新增 MiniMax TTS 引擎并设为默认，默认音色 male-qn-jingying（精英青年）、语速 1.0；API Key 只读取 MINIMAX_API_KEY 环境变量；保留 Kokoro/Edge 可配置切换
  - 2026-05-17: v3.1.0 强化 localhost Kokoro 代理绕过规则——curl/requests 直连本地服务默认必须 NO_PROXY，不允许先走代理失败后重试

author: M.
---

# Text-to-Speech Skill

将文本转换为语音。默认使用 MiniMax TTS（在线高质量中文配音），并保留 Kokoro TTS v1.1-zh（本地 Docker，102 个中文音色）和 Edge TTS（在线）作为可配置后备。

## 引擎对比

| 特性 | MiniMax TTS | Kokoro TTS v1.1-zh | Edge TTS |
|------|-------------|-------------------|----------|
| 质量 | 默认推荐，中文短视频旁白更自然 | 本地可用、接近真人 | 标准 Neural 语音 |
| 网络 | 需要 MiniMax API | 不需要（本地 Docker） | 需要网络连接 |
| 默认音色 | `Chinese (Mandarin)_Reliable_Executive`（可靠高管） | `zm_009` | `zh-CN-YunyangNeural` |
| 语速调节 | speed 参数，默认 1.0 | speed 参数 | rate/pitch/volume |
| 前提 | `MINIMAX_API_KEY` 环境变量 | Docker 容器需运行 | 安装 `edge-tts` |
| 配置值 | `minimax` | `kokoro` | `edge` |

## 使用说明

```bash
# 默认使用 MiniMax TTS（当前配置）
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py <文本文件>

# 指定引擎
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt --engine minimax
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt --engine kokoro
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt --engine edge

# 指定声音
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt -v zf_094

# 指定输出文件
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt -o output.mp3

# MiniMax 专属：同时保存经过校验的词级时间戳
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt \
  -o output.mp3 --subtitle-output output.subtitles.json

# 调整语速（MiniMax/Kokoro）
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt --speed 1.2

# 列出所有可用声音
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py --list-voices
```

## MiniMax TTS

默认配置：

- 引擎：`tts_engine = "minimax"`
- 模型：`speech-2.8-hd`
- 音色：`Chinese (Mandarin)_Reliable_Executive`（可靠高管）
- 语速：`1.0`
- 输出：MP3

### MiniMax 词级时间戳

`--subtitle-output <path>` 会为 MiniMax 请求启用词级时间戳，下载官方 sidecar 后校验文本、字符范围和时间单调性，再写入本地 JSON。sidecar 只保留 `provider/model/voice/subtitle_type/segments`，不会记录官方返回的短期签名 URL。该参数属于 MiniMax 专属能力；Edge/Kokoro 会失败关闭，避免下游误把估算时间当成官方时间戳。

### 整期表达一致性（默认）

`minimax_tts.delivery_consistency` 默认启用 `commercial_narration`。同一期视频内所有句子固定使用相同的音色、速度、音量和音调，不再按每句话的关键词切换表达参数。这样保留真人音色和自然标点韵律，同时避免逐 beat 的语速、声调和情绪跳变。

- 默认档：`commercial_narration`，speed `0.96`、volume `1.0`、pitch `0`
- 显式选择：`--delivery-profile commercial_narration`
- 克隆音色选择顺序：`--voice` > `MINIMAX_VOICE_ID` > 已激活的本机克隆档 > 仓库系统音色
- 本机档：`~/.config/duanku/minimax-voice.json`，必须为 `0600`，不提交仓库

### MiniMax 专属语境适配（兼容回退）

`minimax_tts.context_adaptation` 只在 MiniMax 分支生效。Edge 和 Kokoro 不读取此配置，也不会改变原请求参数。

- 仅当 `delivery_consistency` 关闭时，根据文本自动识别 `opening`、`summary`、`explanation`、`instruction`、`warning`、`resource`、`conclusion`、`call_to_action`、`neutral`
- 语境档只轻量调整 MiniMax 的语速、音量和音高，不修改原文、不注入 emotion、不自动插入声音标签
- 未命中规则时使用 `explanation`
- 可用 `--context warning` 等参数显式覆盖自动识别；选择 Edge/Kokoro 时该参数被忽略
- 调用方无需理解语境规则。视频流水线只需继续提交文本并使用返回音频，音频时长仍由下游实测

```bash
# 自动识别语境
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt

# MiniMax 显式指定风险提醒语境
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt --context warning
```

### MiniMax 声音克隆

声音克隆分为不收费的创建阶段和首次 TTS 激活阶段。首次使用新克隆音色合成会产生官方克隆费及试听字符费，脚本要求 quote ID 和精确金额确认，不能用布尔参数绕过。

**引擎边界**：克隆 profile、克隆 `voice_id`、`--delivery-profile` 和克隆样本门禁只允许在实际 `tts_engine=minimax` 时读取。切换到 Edge 或 Kokoro 后必须完全跳过这些配置，即使本机仍保留已激活的 MiniMax profile，也不得影响非 MiniMax 的音色、请求参数或预检结果。

```bash
# 样本检查，不联网、不收费
python3 scripts/minimax_voice_clone.py inspect --sample /path/to/source.m4a

# 输出激活报价，不联网、不收费
python3 scripts/minimax_voice_clone.py quote \
  --voice-id DuankuNarrator20260801 \
  --text "试听文案"

# 上传并创建克隆，不执行 TTS；必须确认拥有声音授权
python3 scripts/minimax_voice_clone.py clone \
  --sample /path/to/source.m4a \
  --voice-id DuankuNarrator20260801 \
  --rights-confirmed

# 首次付费激活并生成试听，必须使用上一步 quote 的 ID 和金额
python3 scripts/minimax_voice_clone.py activate \
  --text "试听文案" \
  --output /path/to/preview.mp3 \
  --confirm-quote-id '<quote_id>' \
  --confirm-amount-usd '<estimated_total_usd>'
```

样本要求：`mp3/m4a/wav`、10 秒至 5 分钟、最大 20 MB。克隆脚本默认请求 MiniMax 降噪和音量归一化。

密钥规则：

- API Key 只从环境变量读取，默认变量名 `MINIMAX_API_KEY`
- 克隆 `voice_id`、远程 file ID 和激活记录只保存在本机 `0600` profile
- 不要把真实 Key 写进 `config/tts_config.json`、README、命令行参数或提交历史
- 如果要换变量名，只改 `config/tts_config.json` 中的 `minimax_tts.api_key_env`

```bash
export MINIMAX_API_KEY="你的本机 key"
python3 ~/.claude/skills/text-to-speech/scripts/text_to_speech.py script.txt -o output.mp3
```

## Kokoro TTS v1.1-zh 声音

使用 `--list-voices` 查看完整列表（102 个）。

### 推荐声音
- `zm_009` - 男声（默认）
- `zf_094` - 女声（自然温柔）
- `zf_001` - 女声
- `zm_050` - 男声

### 英文声音
- `af_maple` - 女声（Maple）
- `af_sol` - 女声（Sol）
- `bf_vale` - 男声（Vale）

### 声音命名规则
- `zf_XXX` - 中文女声（55 个）
- `zm_XXX` - 中文男声（44 个）
- `af_`/`bf_` - 英文声音（3 个）

## 启动 Kokoro 服务

Kokoro TTS 需要 Docker 容器运行：

```bash
# 启动
cd /Users/m/document/QNSZ/project/kokoro-tts && ./start.sh

# 停止
cd /Users/m/document/QNSZ/project/kokoro-tts && ./stop.sh

# Web UI 试听
# http://localhost:8880/web/
```

## 核心功能

### 1. 脚本解析
自动识别并移除播客脚本中的注释和标记：
- 时间戳：`(00:00)`
- BGM 注释：`[BGM渐入：...]`
- 舞台指示：`(主播声音：...)` `(停顿 1秒)`
- Markdown 标记：`**文本**`

### 2. 中英文混合朗读
v1.1-zh 模型支持中英文混合文本的自然朗读。

### 3. 后处理集成
可选集成 voice-changer skill 进行变声处理。

## 配置文件

配置文件位于：`~/.claude/skills/text-to-speech/config/tts_config.json`

关键配置项：
- `tts_engine`: `"minimax"`、`"kokoro"` 或 `"edge"`（默认引擎）
- `minimax_tts`: MiniMax 引擎配置（API URL、模型、默认音色、语速；Key 仅从环境变量读取）
- `minimax_tts.context_adaptation`: MiniMax 专属语境档和自动识别规则；不影响其他引擎
- `kokoro_tts`: Kokoro 引擎配置（API URL、默认声音、语速）
- `edge_tts`: Edge 引擎配置（声音、语速、音调、音量）
- `available_voices`: 按引擎分组的可用声音列表

## 工作流程

```
输入文本/文件
    ↓
脚本解析（移除注释和标记）
    ↓
MiniMax / Kokoro TTS / Edge TTS 语音合成
    ↓
后处理（voice-changer，可选）
    ↓
输出 MP3 文件
```

## 代理绕过（重要）

Kokoro TTS 运行在 `localhost:8880`。如果系统配置了 HTTP 代理（`http_proxy`/`https_proxy`），请求 localhost 会被代理拦截导致连接失败（curl 返回 HTTP 000）。

**规则**：
- Python 脚本已内置 `os.environ.setdefault("no_proxy", "localhost,127.0.0.1")`，通过脚本调用无需额外处理
- 如果 AI 需要直接用 `curl` 测试或调用 Kokoro API，**必须**加 `--noproxy localhost,127.0.0.1` 或设置 `no_proxy=localhost,127.0.0.1`
- 如果 AI 直接写 Python `requests.post("http://localhost:8880/...")`，必须设置 `proxies={"http": None, "https": None}`，或使用 `requests.Session(); session.trust_env = False`，并设置 `NO_PROXY/no_proxy=localhost,127.0.0.1,::1`
- 禁止不加代理绕过直接 curl/requests localhost；不要先走代理失败再重试，localhost Kokoro 请求默认就必须绕过代理

```bash
# 正确：绕过代理
curl --noproxy localhost,127.0.0.1 -X POST http://localhost:8880/v1/audio/speech ...

# 错误：走了代理，返回 HTTP 000
curl -X POST http://localhost:8880/v1/audio/speech ...
```

## 依赖

- MiniMax TTS: `MINIMAX_API_KEY` 环境变量
- Kokoro TTS: Docker（容器运行在 localhost:8880）
- Edge TTS: `pip install edge-tts`

## 性能参考

- Kokoro TTS: 1000字约 3-5 秒（本地 Docker CPU）
- Edge TTS: 1000字约 10-20 秒（受网络影响）
