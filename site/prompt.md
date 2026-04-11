# 项目网页制作

此项目是用langgraph构建的coding agent CLI

现在需要给项目开发一个类似wiki或者文档的页面，技术栈用next.js + velite

所有前端代码放在site/下，网页的文档来源全部复用docs/

## 必须参考的项目

我有一个个人网站的前端项目，在`~/Documents/code/projects/neuromancer`，同样技术栈。

你需要参考其中的网页组件。


## 网页要求

1. 主题和neuromancer保持一致，深色和浅色支持切换
2. dock栏目最左侧要改成“wiki的logo”（用展开的书的svg，必须轻量） + “项目的名字”， dock栏中间改成这个网页相关的链接，最右侧保持一致。要添加搜索栏目（参考个人网站的blog/的dock栏）
3. 主题内容分为README和文章页面，文章页面主要是渲染markdown，目前docs/下没有mdx格式，所以考虑frontmatter额外处理（最好不要修改docs/的文档）；README是项目介绍，比较大的文字。
4. footer也要搬运过来，最左侧改成项目相关，中间的nvigation也是项目相关，其余一致。

## 注意

如果需要复用`~/Documents/code/projects/neuromancer`的组件，先cp再修改。