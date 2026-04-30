# Context Management Development Plan

本文档基于当前 MT-Agent 实现、[`ClaudeCodeNotes.md`](./ClaudeCodeNotes.md) 的分析，以及本地 Claude Code 源码阅读结果，给 `feature/context` 分支提供一份可执行的开发计划。

参考的 Claude Code 源码重点文件：

- `/Users/chenclay/Documents/code/projects/claude-code-analysis/src/utils/toolResultStorage.ts`
- `/Users/chenclay/Documents/code/projects/claude-code-analysis/src/constants/toolLimits.ts`
- `/Users/chenclay/Documents/code/projects/claude-code-analysis/src/services/compact/autoCompact.ts`
- `/Users/chenclay/Documents/code/projects/claude-code-analysis/src/services/compact/microCompact.ts`
- `/Users/chenclay/Documents/code/projects/claude-code-analysis/src/services/compact/sessionMemoryCompact.ts`
- `/Users/chenclay/Documents/code/projects/claude-code-analysis/src/services/SessionMemory/sessionMemory.ts`
- `/Users/chenclay/Documents/code/projects/claude-code-analysis/src/services/SessionMemory/prompts.ts`

当前 MT-Agent 相关实现：

- [`core/context/manager.py`](../core/context/manager.py): 启动时加载全局 / 项目 context。
- [`core/context/compressor.py`](../core/context/compressor.py): 基础历史摘要压缩。
- [`core/nodes/reasoning.py`](../core/nodes/reasoning.py): 每轮组装 messages、触发压缩、调用 LLM。
- [`core/session/recorder.py`](../core/session/recorder.py): JSONL transcript、resume、压缩记录。
- [`tools/file_ops/read_file.py`](../tools/file_ops/read_file.py): 文件读取工具，已有行范围和截断。
- [`tools/file_ops/grep.py`](../tools/file_ops/grep.py): 搜索工具，当前会把结果直接返回到 ToolMessage。

## 目标

把当前 context v1 升级为可长期运行的 context v2：

1. 每轮发送给 LLM 的上下文有明确预算。
2. 大型工具结果可外置保存，模型只看到必要预览。
3. JSONL transcript 继续作为会话恢复的权威来源。
4. 压缩保留工具调用链、消息边界和最近工作现场。
5. 自动压缩优先使用 session memory，失败后进入 full compact。
6. resume 后能恢复“摘要 + 最近消息 + 工具结果 artifact 引用”。

## 当前差距

### 已具备

- `ContextManager` 已实现 Tier 1 / Tier 2 注入。
- `ContextCompressor` 已能按阈值压缩旧历史。
- `SessionRecorder` 已能保存 JSONL，并基于最后一次 compression 恢复消息。
- `ReadFileTool` 已支持 `start_line` / `end_line`，并限制单次读取行数和字符数。
- LangGraph checkpoint 已接入，支持 execution resume 的基础设施。

### 需要补齐

- 工具结果没有统一预算策略，`grep`、shell 类工具容易把上下文撑大。
- transcript 记录缺少结构化 `toolUseResult` / artifact metadata，UI 展示和 LLM 可见内容还没有分离。
- `ContextCompressor._find_split_point()` 只按消息类型粗略切分，缺少 tool_call / ToolMessage 成对保护。
- 自动压缩阈值是 `token_limit * compression_threshold`，还没有预留摘要输出和安全 buffer。
- 没有 time-based microcompact，旧工具结果会长期污染上下文。
- 没有 session memory compact，压缩只能直接总结完整历史。
- 压缩边界只是摘要消息，缺少显式 `compact_boundary` 记录。

## 设计原则

1. JSONL transcript 是会话事实来源，runtime messages 是每轮请求视图。
2. 工具原始结果、UI 展示结果、LLM 可见结果分开存储。
3. 压缩只改“发送给模型的消息视图”，保留 transcript 和 artifact。
4. 任何 compact 都保留最近工作现场，避免模型失去当前任务状态。
5. 第一版优先实现本项目高频工具：`read_file`、`grep`、`ls`、`edit_file`、`write_file`、后续 shell。

## 目标架构

```text
User / CLI
  |
  v
reasoning_node
  |
  +-- ContextWindowManager
  |     +-- TokenBudget
  |     +-- MicroCompactor
  |     +-- AutoCompactPolicy
  |
  +-- MessageBuilder
        +-- system prompt
        +-- session_context
        +-- compact boundary / session memory
        +-- recent messages
        +-- tool result previews

ToolNode / Tool Wrappers
  |
  +-- ToolResultBudgeter
        +-- LLM-visible preview
        +-- structured artifact
        +-- persisted output file

SessionRecorder
  |
  +-- canonical JSONL
  +-- artifacts/tool-results/*.txt
  +-- session-memory/summary.md
```

建议新增目录：

```text
core/context/
  budget.py
  tool_results.py
  microcompact.py
  session_memory.py
  message_invariants.py

core/session/
  artifacts.py
  schema.py
```

## 里程碑

### M0: 基线整理和指标补齐

目标：先让后续改造可观测、可测试。

改动：

- 在 `SessionStats` 中补充：
  - `last_effective_context_limit`
  - `last_auto_compact_threshold`
  - `last_tool_result_chars`
  - `compression_failure_count`
- 在 `EventType` 中补充：
  - `TOOL_RESULT_PERSISTED`
  - `MICRO_COMPACTED`
  - `SESSION_MEMORY_UPDATED`
  - `COMPACT_BOUNDARY`
- 增加 `core/context/budget.py`：
  - `estimate_message_tokens(messages)`
  - `effective_context_limit(token_limit, reserved_summary_tokens=20000)`
  - `auto_compact_threshold(token_limit, reserved_summary_tokens=20000, buffer_tokens=13000)`

建议配置：

```python
CONTEXT = {
    "token_limit": 131072,
    "summary_reserved_tokens": 20000,
    "autocompact_buffer_tokens": 13000,
    "compression_preserve_min_tokens": 10000,
    "compression_preserve_max_tokens": 40000,
}
```

验收：

- `tests/test_core/test_context_budget.py` 覆盖阈值计算。
- 131072 token 模型的 auto compact 阈值为 `98072`。
- 65536 token 模型的 auto compact 阈值为 `32536`。

### M1: canonical transcript schema 和 artifact 目录

目标：建立 transcript v2，不影响现有 resume。

改动：

- 新增 `core/session/schema.py`，定义业务记录结构：
  - `session_start`
  - `transcript_message`
  - `tool_result_artifact`
  - `compression`
  - `compact_boundary`
  - `session_memory_update`
- 新增 `core/session/artifacts.py`：
  - `get_session_artifact_dir(session_id)`
  - `get_tool_result_path(tool_call_id)`
  - `write_tool_result_artifact(...)`
  - `read_tool_result_artifact(...)`

建议路径：

```text
~/.mtagent/history/<project-hash>/artifacts/<session-id>/
  tool-results/<tool-call-id>.txt
  session-memory/summary.md
```

JSONL 中工具结果记录建议：

```json
{
  "type": "transcript_message",
  "role": "tool",
  "tool_call_id": "...",
  "name": "grep",
  "content": "<persisted-output path=\"tool-results/xxx.txt\" chars=\"120000\">...</persisted-output>",
  "toolUseResult": {
    "kind": "text",
    "artifact": "tool-results/xxx.txt",
    "original_chars": 120000,
    "preview_chars": 4000,
    "truncated": true
  }
}
```

验收：

- 旧 JSONL 能继续通过 `build_resume_messages()` 恢复。
- 新 JSONL 的 artifact 相对路径能在 resume 时解析。
- artifact 文件最大保留 64MB，超过后截断并记录 `truncated=true`。

### M2: Tool Result Budget

目标：工具结果进入 LangGraph state 前完成预算处理。

改动：

- 新增 `core/context/tool_results.py`：
  - `ToolResultPolicy`
  - `ToolResultBudgeter`
  - `map_tool_result_for_llm(tool_name, content, artifact_meta)`
- 在 `create_event_bus_wrapper()` 或 ToolNode 后处理层接入 budgeter。
- 为工具声明默认阈值：
  - `grep`: 20_000 chars
  - shell 类: 30_000 chars
  - read_file: 走自身行范围和 token 限制，默认不直接外置完整文件
  - default: 50_000 chars
  - per message aggregate: 200_000 chars

LLM 可见输出格式：

```text
<persisted-output tool="grep" path="tool-results/<id>.txt" original_chars="120000">
Found 240 matches. Showing first 80 lines:
...
</persisted-output>
```

验收：

- `grep` 返回 20K 以上内容时，ToolMessage 中只保留预览。
- artifact 文件保存完整或 64MB 截断内容。
- session JSONL 同时记录 LLM 可见 preview 和结构化 artifact metadata。
- UI 仍可通过 transcript/artifact 展示完整工具结果摘要。

### M3: ReadFileTool 升级

目标：让读取大文件的行为更接近 Claude Code 的 `Read` 策略。

改动：

- 将 `ReadFileTool` 参数统一为：
  - `file_path`
  - `offset`
  - `limit`
  - 保留兼容 `start_line` / `end_line`
- 新增读取状态缓存：
  - key: `file_path + offset + limit + mtime`
  - 命中时返回 `file_unchanged` stub。
- 增加限制：
  - 默认 `max_size_bytes=256KB`
  - 默认 `max_tokens=25000`
  - 未传范围且文件过大时提示使用 `offset/limit`
  - 传范围时只读取指定行段
- LLM 可见内容带行号。
- `toolUseResult` 保留：
  - `file_path`
  - `content`
  - `start_line`
  - `num_lines`
  - `total_lines`
  - `mtime`

验收：

- 大文件无范围读取给出明确错误和继续读取建议。
- 分段读取输出带行号。
- 同一文件、同一范围、mtime 未变时返回 `file_unchanged`。
- resume 后 UI 可以根据 `toolUseResult` 展示读取范围。

### M4: Auto Compact 策略重写

目标：压缩触发从固定比例升级为“有效窗口 + buffer”。

改动：

- `ContextCompressor.should_compress()` 接收当前 token 和 policy 结果。
- 新增 `AutoCompactPolicy`：
  - 跳过 compact query source
  - 连续失败 3 次熔断
  - 基于 `auto_compact_threshold()` 判断触发
  - 记录压缩前后 token
- `reasoning_node` 每轮构建 messages 后先做：
  - token 估算
  - microcompact
  - auto compact
  - 重新估算
  - LLM 调用

验收：

- token 未达到阈值时不压缩。
- token 达到 `token_limit - 20000 - 13000` 时触发。
- 连续 3 次压缩失败后本 session 不再自动压缩，并发出事件。
- reactive compact 仍可在 context length 400 错误后强制执行。

### M5: Compact Boundary 和消息不变量

目标：压缩后不破坏 LangChain / OpenAI function-calling 消息结构。

改动：

- 新增 `core/context/message_invariants.py`：
  - `find_safe_split_index(messages)`
  - `adjust_index_to_preserve_tool_pairs(messages, index)`
  - `adjust_index_to_preserve_message_groups(messages, index)`
  - `find_last_compact_boundary(messages)`
- `ContextCompressor._find_split_point()` 改为：
  - 保留区域至少约 10K tokens
  - 保留区域最多约 40K tokens
  - 不跨越上一条 compact boundary
  - 不拆 `AIMessage.tool_calls` 和对应 `ToolMessage`
  - 不拆同一轮 assistant chunk 合并后的消息组
- `build_summary_message()` 前插入显式 boundary：

```text
<compact_boundary pre_tokens="..." post_tokens="..." reason="auto" />
```

验收：

- 有 tool call 的消息序列压缩后仍能被模型 API 接受。
- 多次压缩时只压缩最近 boundary 之前可压缩的区域。
- JSONL 中有 `compact_boundary` 记录，可用于 resume 和调试。

### M6: Session Memory Compact

目标：把“后台结构化笔记”作为 auto compact 的第一选择。

第一版可以同步执行，不必立即实现 forked agent。

改动：

- 新增 `core/context/session_memory.py`：
  - `DEFAULT_SESSION_MEMORY_TEMPLATE`
  - `SessionMemoryManager`
  - `should_extract_memory(messages, token_count, tool_call_count)`
  - `update_session_memory(messages)`
  - `try_session_memory_compact(messages)`
- session memory 文件路径：

```text
~/.mtagent/history/<project-hash>/artifacts/<session-id>/session-memory/summary.md
```

触发建议：

- 初始化：当前上下文超过 10K tokens。
- 更新：距离上次提取增长超过 5K tokens。
- 工具调用条件：上次提取后工具调用达到 3 次，或最近 assistant turn 没有工具调用。

模板采用你笔记中 Claude Code 的 section：

- Session Title
- Current State
- Task specification
- Files and Functions
- Workflow
- Errors & Corrections
- Codebase and System Documentation
- Learnings
- Key results
- Worklog

compact 逻辑：

1. 等待或执行最新 session memory 更新。
2. 找到 `last_summarized_message_id`。
3. 从该位置之后保留 recent messages。
4. recent messages 太少时向前扩展到约 10K tokens。
5. 若 compact 后仍超过 auto compact 阈值，回退 full compact。

验收：

- `summary.md` 首次自动创建。
- memory 更新只改模板内容区，保留标题和说明行。
- auto compact 优先用 session memory summary。
- resume 后能加载 `summary.md` 并恢复最近消息。

### M7: Time-Based Microcompact

目标：长时间暂停后清理旧工具结果，减少下一轮请求成本。

改动：

- 新增 `core/context/microcompact.py`：
  - `maybe_time_based_microcompact(messages, now, last_assistant_ts)`
  - `compactable_tool_names = {"read_file", "grep", "glob", "ls", "edit_file", "write_file", "shell"}`
  - `gap_threshold_minutes = 60`
  - `keep_recent = 5`
- 清理策略：
  - 只替换 LLM 可见 ToolMessage 内容。
  - artifact 和 JSONL 原始记录保留。
  - 最近 5 个工具结果保留。

替换内容：

```text
[Old tool result content cleared. Full result is available in the session transcript artifact.]
```

验收：

- 距离上次 assistant 消息超过 60 分钟时触发。
- 旧工具结果被清理，最近 5 个保留。
- transcript / artifact 中仍能查到完整结果。

### M8: Partial Compact 和 CLI 命令

目标：提供手动可控的上下文整理能力。

改动：

- `/compact`：
  - 无参数：优先 session memory compact。
  - 有指令：执行 full compact，并把指令拼入 compact prompt。
- `/compact from <message-id>`：
  - 从指定消息开始做 partial compact。
  - 保留指定位置之后的消息。
- `/context stats`：
  - 展示 system / session / history / tool result token 估算。
  - 展示 auto compact 阈值和距离阈值的剩余 tokens。
- `/context artifacts`：
  - 列出当前 session 的外置工具结果。

验收：

- 手动 `/compact` 会写入 `compact_boundary`。
- partial compact 不拆工具调用链。
- CLI 能展示压缩前后 token 变化。

## 推荐开发顺序

1. M0 + M1：先补 schema、artifact 和指标。
2. M2 + M3：先解决工具结果膨胀，这是 coding agent 最容易爆上下文的来源。
3. M5：补安全切分，再改压缩策略。
4. M4：接入新的 auto compact policy。
5. M6：引入 session memory compact。
6. M7：加入 time-based microcompact。
7. M8：补 CLI 手动能力和调试入口。

这个顺序可以保持每个阶段都有可验证收益：

- M2 完成后，大搜索和命令输出不会直接污染上下文。
- M3 完成后，大文件读取能稳定分段。
- M5 完成后，压缩不会破坏工具消息结构。
- M6 完成后，长会话恢复质量明显提升。

## 测试计划

### 单元测试

- `tests/test_core/test_context_budget.py`
  - token 阈值计算
  - auto compact policy
  - 连续失败熔断
- `tests/test_core/test_tool_result_budget.py`
  - 单工具阈值
  - aggregate 200K 阈值
  - artifact 写入和截断
- `tests/test_core/test_read_file_budget.py`
  - 大文件无范围读取
  - offset/limit 分段
  - file unchanged
- `tests/test_core/test_message_invariants.py`
  - tool_call / ToolMessage 不拆分
  - compact boundary 不跨越
  - recent tokens 扩展规则
- `tests/test_core/test_session_memory.py`
  - 模板创建
  - 更新触发条件
  - compact 后消息结构

### 集成测试

- 构造长对话 + 大 grep 输出，验证：
  - artifact 写入
  - ToolMessage 预览
  - auto compact 触发
  - JSONL resume 恢复摘要和最近消息
- 构造带工具审批的会话，验证：
  - compact 不影响 checkpoint-first resume
  - interrupted 工具不会被重复执行
- 构造多次 compact，验证：
  - boundary 正确
  - 只保留最新有效压缩视图

## 风险和取舍

- LangChain `ToolMessage` 对 artifact metadata 的承载能力有限，建议把 artifact metadata 放进 JSONL record，并在 ToolMessage content 中放轻量 XML 标记。
- Python 版本没有 Claude Code 的服务端 cache editing 能力，cached microcompact 暂缓实现。
- session memory 第一版同步执行即可，后续再升级为后台任务或子图。
- token 估算仍是启发式，保留 `BadRequestError` reactive compact 作为兜底。
- shell 工具接入后需要更严格的安全策略，建议在工具结果预算稳定后再做。

## 完成标准

Context v2 完成时，应满足：

1. 长时间 MT-3000 kernel 优化会话可以持续运行，不因 grep / compile / benchmark 输出快速耗尽上下文。
2. `/resume` 后模型能看到当前任务、关键文件、最近操作和压缩摘要。
3. 用户能从 JSONL 和 artifacts 找回完整工具结果。
4. 自动压缩有阈值、有边界、有失败熔断。
5. 每个压缩动作都有事件、日志和 session record。
6. 单元测试覆盖预算、artifact、read file、message invariants、session memory。
