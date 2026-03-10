# MT-3000平台自动代码优化工具

此项目基于`~/YangChen/mt-vectorizer-tool`

改用skill的概念重构。

一个标准的 Skill 包含以下结构：

```text
pdf-skill/              # 在skills目录下
├── SKILL.md            # Skill 元数据和核心指令（必需）
├── forms.md            # 表单填写指南（可选）
├── reference.md        # 详细 API 参考（可选）
└── scripts/            # 实用脚本
    └── extract_fields.py
```

比如`SKILL.md`中:

```markdown
---
name: pdf-processing
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
---

# PDF Processing

## Quick start

Use pdfplumber to extract text from PDFs...

For advanced form filling, see [forms.md](forms.md).
```

三级渐进式加载机制
Level 1：元数据（始终加载）

启动时，Claude 仅加载每个 Skill 的 YAML frontmatter（ name 和 description ），并将其包含在系统提示词中。

Level 2：指令（触发时加载）

如果 Claude 认为该skill与当前任务相关，它会读取完整的 SKILL.md 文件并将其加载到上下文中。

Level 3：资源和代码（按需加载）

随着skill复杂性的增加，它们可能包含过多的上下文信息，无法放入单个 SKILL.md 文件中，或者包含仅在特定场景下才相关的上下文信息。在这种情况下，可以在skill目录中映射其他文件，并在 SKILL.md 文件中按名称引用这些文件。

## 环境配置

创建python=3.10版本的conda虚拟环境，名字为项目名`mt-autooptimize`。

## 生成开发计划

首先要确定需要的背景知识，比如mt3000平台的背景，集中存储/缓存的大小。

hthreads编程的接口文档。

AM代码的模版

SM代码的模版

(或许还有别的)

这些都封装到skills吧


### 明确项目目录结构

开发的内容一定要低耦合，符合软件开发的标准。

### LLM部分可以设定轮询

可能需要用到langchain之类的工具


### API部分要采用配置文件/环境变量读取

安全性考量

### 编译/测试结果的展示

编译和测试结果也需要输出

开发计划请生成markdown存储在此目录中，名称为`plan.md`