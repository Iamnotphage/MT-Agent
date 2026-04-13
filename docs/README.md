# MT-Agent

Coding Agent for MT-3000

此文档辅助理解和开发

---

## 开发环境

必备工具:

* [uv](https://docs.astral.sh/uv/) 包管理器，创建虚拟环境辅助开发


## 子文档阅读顺序

1. [Architecture](./Architecture.md): 三层架构总览（CLI → Core → Tools），依赖规则和数据流
2. [ReActLoop](./ReActLoop.md): ReAct 循环详解，状态定义和各节点职责
3. [EventBus](./EventBus.md): 事件总线机制，14 种事件类型和完整事件流
4. [Tools](./Tools.md): 工具层，内外部工具的schema和注册相关内容
5. [Context&Memory](./Context&Memory.md): 启动时上下文加载与长期 memory 管理
6. [Session](./Session.md): 会话保存、历史压缩、/resume 恢复与 checkpoint 机制
