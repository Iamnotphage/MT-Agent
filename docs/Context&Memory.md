# Context & Memory

当前项目的 context 与 memory 已经形成一个可用的 v1 闭环，重点解决两件事：

1. 启动时加载全局 / 项目上下文
2. 在长会话中压缩上下文，并跨会话保存长期 memory

## 当前结构

### 1. 静态 Context

由 [`core/context/manager.py`](../core/context/manager.py) 管理，分为两层：

- Tier 1: 全局 `CONTEXT.md`
  注入到 system prompt，适合放全局规则、长期偏好、Agent memory。
- Tier 2: 项目 `CONTEXT.md`
  注入到首轮 `<session_context>`，适合放当前项目说明。

当前 `ContextManager` 负责：

- 加载全局 / 项目 context
- 构建 system context
- 构建 session context
- 提供基础 token / 文件统计

## 一次会话实际传给 LLM 的内容

这部分由 [`core/nodes/reasoning.py`](../core/nodes/reasoning.py) 和 [`prompts/system_prompt.py`](../prompts/system_prompt.py) 共同决定。

每一轮推理时，真正传给 LLM 的 `messages` 顺序是：

1. `SystemMessage`
2. 首轮额外注入的 `session_context`（只在 turn 0）
3. 历史消息 `state.message`
4. 若触发压缩，则历史消息会被替换为“压缩摘要 + 最近消息”

也就是说，当前模型看到的不是单一 prompt 字符串，而是：

- 一条动态生成的 system message
- 一条仅首轮存在的 session context human message
- 多条用户 / assistant / tool 历史消息

### 1. SystemMessage 里有什么

`SystemMessage` 的模板定义在 [`prompts/system_prompt.py`](../prompts/system_prompt.py)。

它由四部分拼起来：

1. 固定系统提示词模板
2. 工具列表 `tool_section`
3. 全局上下文 `global_context_section`
4. 运行时上下文 `runtime_context_section`

#### 固定部分

这部分是模板中的常量文本，例如：

- Agent 身份
- 工作原则
- 回答语言
- 何时使用 `save_memory`

这些内容对所有会话都存在，除非你修改模板本身。

#### 可变的 `{}` 动态部分

当前模板中的可变部分包括：

- `{tool_section}`
- `{global_context_section}`
- `{runtime_context_section}`

它们分别对应：

- 当前注册到 runtime 中的工具 schema 列表
- `ContextManager.build_system_context()` 返回的 Tier 1 全局 context
- 当前 `AgentState` 里的运行时字段

#### 工具列表

工具列表来自 `tool_schemas`，会被渲染成：

- 工具名
- 工具描述

这一部分是每轮动态生成的，但通常在一次运行期间相对稳定。

#### 全局 Context

这部分来自全局 `CONTEXT.md`，由 `ContextManager.build_system_context()` 返回。

当前包含：

- 全局规则
- 全局偏好
- `## Agent Memories` 中的长期 memory

它被直接拼进 system prompt，因此对每一轮都生效。

#### 运行时 Context

这部分来自当前 `AgentState`，属于每轮都可能变化的 `{}` 内容。

当前会按需注入：

- `optimization_mode`
- `source_file`
- `working_directory`

如果这些字段为空，对应 section 就不会出现。

### 2. 首轮的 `<session_context>` 里有什么

`session_context` 只在第一轮作为一条额外的 `HumanMessage` 注入。

它由 [`core/context/manager.py`](../core/context/manager.py) 中的 `build_session_context()` 构建，当前包含：

- Today's date
- OS
- Working directory
- 项目级 `CONTEXT.md` 内容

因此：

- Tier 1 全局 context → 每轮进入 `SystemMessage`
- Tier 2 项目 context → 只在首轮作为 `<session_context>` 注入

这个分层是当前实现里最重要的设计点。

### 3. 历史消息里有什么

历史消息来自 `state.message`，当前可能包括：

- `HumanMessage`
- `AIMessage`
- `ToolMessage`
- 压缩后插入的摘要消息

这些消息会在每轮推理时被追加到 system message 后面，一起发送给 LLM。

---

## 上下文压缩

上下文压缩仍然属于 Context 管理的一部分，因为它直接决定“当前这一轮要把哪些历史发给 LLM”。

实现位于：

- [`core/context/compressor.py`](../core/context/compressor.py)
- [`core/nodes/reasoning.py`](../core/nodes/reasoning.py)

### 1. 何时触发

当前根据最近一次输入 token 数判断是否压缩：

- `last_input_tokens >= token_limit * compression_threshold`

其中：

- `token_limit`
- `compression_threshold`
- `compression_preserve_ratio`

来自 [`config/settings.py`](../config/settings.py)。

### 2. 如何压缩

当前策略是：

1. 取出 `state.message` 全部历史
2. 保留最近一部分消息
3. 选择更早的消息作为压缩对象
4. 调用压缩专用 prompt 生成结构化摘要
5. 用一条 `<conversation_history_summary>` 消息替换旧历史

压缩后，当前轮实际发给模型的是：

- `SystemMessage`
- 首轮 `session_context`（若仍在首轮）
- `summary_message`
- 最近保留的若干条消息

### 3. 压缩结果长什么样

压缩摘要会被包装成一条 `HumanMessage`：

```text
<conversation_history_summary>
...
</conversation_history_summary>
```

这样做的目的不是把摘要写进 system prompt，而是把它作为“历史快照消息”插入到消息序列里。

### 4. 为什么它也写入 session

压缩结果不仅在当轮生效，还会写入 session JSONL：

- `compression`
- `summary`
- `removed_count`
- `kept_count`

这解决了两个问题：

- 压缩不再只是内存态
- 后续 `/resume` 可以从最后一次压缩摘要继续恢复上下文视图

## 2. Memory

memory 由 [`core/memory/manager.py`](../core/memory/manager.py) 管理，
runtime 在组装阶段把它与 [`core/context/manager.py`](../core/context/manager.py) 的
全局 context 缓存刷新回调连接起来，
目前是最简单的持久化 facts 方案：

- 存储位置：全局 `CONTEXT.md` 的 `## Agent Memories` 区域
- 写入方式：追加 markdown list item
- 读取方式：启动时一并加载到全局 context

当前能力：

- Agent 可通过 `save_memory` tool 持久化一条 fact
- CLI 支持 `/memory list|add|remove`
- memory 对人类可见、可手工编辑

当前限制：

- 还没有 relevance retrieval
- 还没有去重、失效、冲突处理
- 还没有 project-scoped memory

## Context / Compression / Memory 的边界

这三者在当前实现中的职责是：

- Context
  启动时和每轮推理时注入什么背景信息
- Compression
  当历史太长时，如何缩短“本轮真正发给 LLM 的消息”
- Memory
  什么信息值得跨会话长期保存

因此：

- Context 关注“注入什么”
- Compression 关注“删掉什么、保留什么”
- Memory 关注“长期记住什么”

## Session 文档

当前会话保存、压缩、恢复、checkpoint 的实现已经足够独立成篇，已单独整理到：

- [Session](./Session.md)

建议阅读顺序：

1. 先看本文，理解启动时加载什么、每轮给 LLM 传什么、如何压缩上下文、长期记住什么
2. 再看 [Session](./Session.md)，理解会话如何保存、恢复、以及 checkpoint 如何参与 `/resume`
