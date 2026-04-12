# Session

当前项目的 session 能力已经形成一个可用的 v1，重点覆盖三件事：

1. 持久化保存会话历史
2. 在长会话中压缩历史上下文
3. 基于 transcript + checkpoint 恢复会话

---

## 1. Session 保存什么

当前会话状态分成两类持久化：

- JSONL transcript
  负责记录“过去发生了什么”
- SQLite checkpoint
  负责记录“图执行停在什么地方”

两者职责不同，不能互相替代。

### 1.1 JSONL transcript

由 [`core/session.py`](../core/session.py) 中的 `SessionRecorder` 负责。

保存路径：

`~/.mtagent/history/<project-hash>/session-<timestamp>-<session-id>.jsonl`

其中：

- `<project-hash>` 基于工作目录路径计算
- 一个项目的历史会话统一放在同一个目录下

session 文件中主要包含：

- `session_start`
- `transcript_message`
- `compression`
- `approval_request`
- `approval_decision`
- `session_end`

其中用于恢复对话语义的 canonical transcript 是 `transcript_message`：

- `role=user`
- `role=assistant`，可带 `tool_calls`
- `role=tool`，可带 `tool_call_id`

### 1.2 SQLite checkpoint

由 LangGraph SQLite checkpointer 持久化，接入点在 [`core/agent.py`](../core/agent.py)。

保存路径：

`~/.mtagent/history/<project-hash>/checkpoints.sqlite`

它保存的是 LangGraph 的 checkpoint state，而不是 transcript 文本。

当前主要用于恢复：

- `message`
- `pending_tool_calls`
- `completed_tool_calls`
- `approval_requests`
- `needs_human_approval`
- graph 当前的 `next` / interrupt 状态

结论是：

- JSONL 负责历史展示、resume 的 transcript fallback、压缩摘要恢复
- SQLite 负责 execution resume

---

## 2. 如何保存会话

### 2.1 运行时记录

在一次会话进行过程中，CLI / Core 会不断向 `SessionRecorder` 追加记录。

关键入口包括：

- [`core/nodes/reasoning.py`](../core/nodes/reasoning.py)
  记录 assistant transcript、compression
- [`core/nodes/observation.py`](../core/nodes/observation.py)
  记录 tool transcript
- [`cli/event_handlers/stream.py`](../cli/event_handlers/stream.py)
  记录审批事件、工具展示事件

### 2.2 退出时 flush

退出时由 `SessionRecorder.flush()` 落盘。

它会写入：

1. `session_start`
2. 全部业务记录
3. `session_end`

如果当前会话是从旧 session resume 出来的，还会：

- 先合并旧 session 的历史记录
- 再写入新文件
- 最后删除旧文件

这样可保证 resume 后仍然只有一个最新 session 文件，而不是把一段连续会话拆成多个碎片文件。

---

## 3. 长会话如何压缩

历史压缩由 [`core/compressor.py`](../core/compressor.py) 和 [`core/nodes/reasoning.py`](../core/nodes/reasoning.py) 负责。

触发条件：

- 最近一次输入 token 超过 `token_limit * compression_threshold`

压缩策略：

1. 保留最近一部分消息
2. 选择更早历史作为压缩对象
3. 用 LLM 生成结构化摘要
4. 当前轮直接使用“摘要 + 最近消息”的压缩视图继续推理

压缩结果会写入 JSONL：

- `compression`
- `summary`
- `removed_count`
- `kept_count`

这意味着压缩不是只在内存里发生，而是成为 session 历史的一部分，后续 resume 也能利用它。

---

## 4. 如何恢复会话

当前 `/resume` 由 [`cli/commands/resume.py`](../cli/commands/resume.py) 实现。

### 4.1 transcript 恢复

基础恢复路径是：

1. 读取 session JSONL
2. 找到最后一条 `compression`
3. 只恢复该摘要及其后的 transcript
4. 重建 LangChain 消息对象

重建结果包括：

- `HumanMessage`
- `AIMessage(tool_calls=...)`
- `ToolMessage`

因此当前 resume 已经不是简单的“恢复聊天文本”，而是能恢复：

- 用户消息
- assistant 的 tool call 语义
- tool result 对话历史

### 4.2 checkpoint-first execution resume

当前 `/resume` 优先尝试 execution resume：

1. 从 session JSONL 中读取 `threadId`
2. 调用 `graph.get_state(config)`
3. 从 `checkpoints.sqlite` 中取回该 thread 最近的 checkpoint
4. 若 checkpoint 可恢复，则以 checkpoint 为准恢复执行态

也就是说：

- transcript 恢复解决“模型看过什么”
- checkpoint 恢复解决“图停在哪里”

---

## 5. 恢复边界与安全策略

### 5.1 工具执行中断

若恢复时发现 graph 停在 `tool_execution`，且存在尚未完成的 `pending_tool_calls`：

- 系统不会自动重跑工具
- 而是将这些工具调用收敛为 `interrupted`
- 并写入中断提示消息后结束该未完成执行链

这样可以避免 resume 后重复执行高风险工具。

### 5.2 审批恢复

若 checkpoint 中存在 `awaiting_approval`：

- 必须同时存在可恢复的审批 interrupt 请求
- 若状态不一致，则拒绝恢复执行现场
- 若审批请求存在，则恢复后重新请求确认

当前规则是：

- 仍处于 `awaiting_approval` → 重新确认
- 已进入 `tool_execution` 但未完成 → 标记 `interrupted`
- 已完成 → 不重放审批，也不重放工具执行

### 5.3 一致性检查

当前 `/resume` 还会做 checkpoint / transcript 一致性检查。

优先级如下：

1. execution resume 以 checkpoint 为准
2. transcript 用于历史展示、压缩摘要恢复、fallback token 估算
3. compression 只影响 transcript/history，不覆盖 checkpoint 的执行语义

当前已处理的场景：

- session 缺少 `threadId` → 拒绝 execution resume
- 找不到持久化 checkpoint → 拒绝 execution resume
- 存在 `awaiting_approval`，但没有可恢复的审批请求 → 拒绝 execution resume
- checkpoint 与 transcript 历史长度不一致 → 允许恢复，但明确提示“以 checkpoint 为准”
- checkpoint 有状态但 transcript 不完整 → 允许恢复，但提示历史展示可能不完整

---

## 6. 调试方式

### 6.1 查看 session 历史

可直接查看 JSONL：

```bash
ls ~/.mtagent/history/<project-hash>/
cat ~/.mtagent/history/<project-hash>/session-*.jsonl
```

### 6.2 查看 checkpoint

可用 sqlite 工具排障：

```bash
sqlite3 ~/.mtagent/history/<project-hash>/checkpoints.sqlite
```

常见查看方式：

```sql
.tables
.schema
SELECT name FROM sqlite_master WHERE type='table';
```

需要注意：

- `checkpoints.sqlite` 是 LangGraph 内部状态库
- 可以用于调试
- 不建议业务代码直接依赖其内部表结构

---

## 7. 与 Context / Memory 的边界

Session、Context、Memory 在当前项目中的职责边界如下：

- Context
  启动时注入的静态背景信息
- Memory
  跨会话持久化的长期 facts
- Session
  当前会话产生的历史、压缩摘要、恢复状态、checkpoint

