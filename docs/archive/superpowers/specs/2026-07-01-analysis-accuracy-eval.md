# 失败分析准确率评估 设计文档

**日期**: 2026-07-01
**版本**: v1.0

---

## 1. 概述

### 1.1 背景

项目已有 CI 失败分析功能（`job_failure_analysis` 表），AI 会自动分析失败 job 的日志，输出 `root_cause_summary`（根因）和 `improvement_measures_summary`（修复建议）。

同时 `matches_v5.xlsx` 记录了失败 job 与实际修复 PR 的对应关系（通过 `/nightly` 评论精准匹配）。

现在需要将两者结合，评估 AI 分析的质量——AI 的诊断和建议是否和实际修复一致。

### 1.2 目标

构建评估脚本，对 AI 失败分析结果进行自动化评分：
1. **根因准确率**：AI 的 `root_cause_summary` 是否命中了实际问题的根因？
2. **修复准确率**：AI 的 `improvement_measures_summary` 是否与 PR 的实际修改一致？

### 1.3 Ground Truth

使用 `matches_v5.xlsx` 中 `match_type=triggered` 的行作为 ground truth（PR 通过 `/nightly` 评论确认与失败 job 关联）。

---

## 2. 架构

### 2.1 文件结构

```
analysis_eval/                          # 根目录下
├── evaluate.py                         # 主评估脚本
├── prompt.py                           # LLM Judge prompt 模板
├── README.md                           # 使用说明
└── eval_result.xlsx                    # 评估报告输出
```

### 2.2 数据流

```
matches_v5.xlsx (triggered only)
         │
         ├── job_id ← → job_failure_analysis (DB)
         │
         ├── GitHub API → PR 详情 (title, body)
         │
         ▼
    LLM Judge 评估
         │
         ├── root_cause_score (0-10)
         ├── improvement_score (0-10)
         └── judge_reasoning
         │
         ▼
    eval_result.xlsx
```

### 2.3 不存数据库

评估结果仅输出到 Excel，不创建数据库表。

---

## 3. LLM Judge 设计

### 3.1 Prompt 模板

```
你是一个 CI 失败分析评估专家。请评估以下 AI 分析的质量。

【失败 Job 信息】
- Workflow: {workflow_name}
- Job Name: {job_name}
- 失败时间: {failure_date}

【AI 根因分析】
{root_cause_summary}

【AI 修复建议】
{improvement_measures_summary}

【实际修复 PR】
- 标题: {pr_title}
- 描述: {pr_body}

请分别打分 (0-10，保留 1 位小数)：
1. **根因分析准确度**：AI 的诊断是否准确识别了问题的根本原因？
   - 10 = 完全命中根因
   - 5 = 方向对但细节不足
   - 0 = 完全错误

2. **修复建议准确度**：AI 的修复建议是否与 PR 的实际修改一致？
   - 10 = 建议与 PR 改动高度吻合
   - 5 = 部分相关但不精确
   - 0 = 完全不相关

请严格按以下 JSON 格式输出，不要输出其他内容：
{"root_cause_score": N, "improvement_score": N, "reasoning": "你的判断理由"}
```

### 3.2 评分维度

| 维度 | 评分依据 |
|------|---------|
| root_cause_score | AI 根因 vs PR 标题+描述的语义吻合度 |
| improvement_score | AI 建议的修改方向 vs PR 的实际改动 |

### 3.3 人工抽查

- 从评估结果中随机抽取 10% 进行人工复核
- `eval_result.xlsx` 中预留 `human_review` 列用于标注

---

## 4. 实现要点

### 4.1 evaluate.py

- 读取 `matches_v5.xlsx`，过滤 `match_type=triggered` 的行
- 按 `job_id` 查询 `job_failure_analysis` 表
- 筛选 `analysis_status='completed'` 且有有效 `root_cause_summary` 的记录
- 通过 GitHub API 拉取对应 PR 的标题和 body
- 调用 LLM（复用项目已有的 LLM 客户端）进行打分
- 输出 Excel 报告，包含：job_id, workflow, model, failure_date, root_cause_summary, improvement_measures_summary, pr_number, pr_title, root_cause_score, improvement_score, judge_reasoning

### 4.2 prompt.py

- 维护 prompt 模板
- 支持变量替换

---

## 5. 使用方式

```bash
cd analysis_eval
python evaluate.py --matches ../backend/matches_v5.xlsx --output eval_result.xlsx
```

---

## 6. 待决策

- [ ] LLM Judge 使用哪个模型？（默认复用项目配置的活跃 LLM provider）
- [ ] 人工抽查需要什么样的 UI？（目前先 Excel 标注）
