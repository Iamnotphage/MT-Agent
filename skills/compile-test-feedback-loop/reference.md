# 编译测试反馈闭环参考

## 1) 编译步骤（参考项目实践）

1. `compile`: `.dev.c -> .dev.o`
2. `link`: `.dev.o -> .dev.out`
3. `makedat`: `.dev.out -> .dev.dat`

## 2) 错误信息抽取

建议对每个步骤采集：

- `step`
- `returncode`
- `stdout`
- `stderr`

并优先将 `stderr` 回灌给下一轮 LLM 生成。

## 3) 重试提示模板（建议）

- 上一轮代码（assistant）
- 当前错误（user）
- 约束：
  - 仅返回完整 C 代码
  - 保持目标函数后缀（`_vec_qwen` 或 `_sca_qwen`）
  - 不要输出 markdown 包裹

## 4) 结果报告字段

- 输入路径、输出路径
- AM/SM 模式与模板选择
- 重试次数
- 每轮编译结果
- 最终状态（success/failed）

