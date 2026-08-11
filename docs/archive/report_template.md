# 报告示例模版和字段说明

## 报告格式（JSON）

```json
{
  "model_name": "Qwen/Qwen3-0.6B",
  "hardware": "A2",
  "dtype": "bffloat16",
  "feature": ["mlp_prefetch"],
  "vllm_version": "0.18.0",
  "vllm_ascend_version": "releases/v0.18.0",
  "tasks": [
    {
      "name": "GSM8K-in3500-bs2800",
      "metrics": {
        "Prefill_Token_Throughput": 634.19,
        "Input_Token_Throughput": 848.38,
        "Output_Token_Throughput": 347.75,
        "Total_Token_Throughput": 1196.13
      },
      "test_input": {
        "num_prompts": 1,
        "max_out_len": 3000,
        "batch_size": 1,
        "request_rate": 11.2
      },
      "target": {
        "baseline": 1,
        "threshold": 0.97
      },
      "pass_fail": "pass"
    },
    {
      "name": "gsm8k-lite",
      "metrics": {
        "accuracy": 100
      },
      "test_input": {
        "max_out_len": 4096,
        "batch_size": 64
      },
      "target": {
        "baseline": 1,
        "threshold": 0.97
      },
      "pass_fail": "pass"
    }
  ],
  "serve_cmd": {
    "mix": "vllm server --model Qwen/Qwen3-0.6B --tensor-parallel-size 4"
  },
  "environment": {
    "ASCEND_RT_VISIBLE_DEVICES": "0,1,2,3",
    "PYTORCH_NPU_ALLOC_CONF": "max_split_size_mb=32"
  }
}
```

## serve_cmd 格式说明

### 标准部署（mix）模式

```json
{
  "serve_cmd": {
    "mix": "vllm server --model Qwen/Qwen3-32B --tensor-parallel-size 4"
  }
}
```

### PD 分离（pd）模式

```json
{
  "serve_cmd": {
    "pd": {
      "prefill-0": "vllm server --model Qwen/Qwen3-32B --role prefill --tensor-parallel-size 4",
      "prefill-1": "vllm server --model Qwen/Qwen3-32B --role prefill --tensor-parallel-size 4",
      "decode-0": "vllm server --model Qwen/Qwen3-32B --role decode --tensor-parallel-size 2",
      "decode-1": "ENV1=aaa vllm server --model Qwen/Qwen3-32B --role decode --tensor-parallel-size 2"
    }
  }
}
```

**注意：**
- `mix` 和 `pd` 是互斥的，只能使用其中一种
- PD 分离模式下，每个节点都需要完整的启动命令
- 可以在命令前添加环境变量，如 `ENV1=aaa vllm server ...`

## 字段说明

### 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model_name` | string | 是 | 模型名称，如 Qwen/Qwen3-32B |
| `hardware` | string | 是 | 硬件类型：A2, A3, 310P 等 |
| `dtype` | string | 否 | 权重类型：w8a8, fp16, bf16 等 |
| `feature` | array | 否 | 启用的特性列表：["mlp_prefetch", "bbb"] |
| `vllm_version` | string | 否 | vLLM 版本：0.18.0, 0.19.0 等 |
| `vllm_ascend_version` | string | 否 | vLLM Ascend 版本 |
| `tasks` | array | 是 | 测试任务列表 |
| `serve_cmd` | object | 否 | 启动命令：`{ mix: '...' }` 或 `{ pd: {...} }` |
| `environment` | object | 否 | 环境变量：`{ ENV1: 'aaa', ... }` |

### Task 结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 任务名称，如 GSM8K-in3500-bs2800 |
| `metrics` | object | 性能指标键值对，如 Throughput、Accuracy 等 |
| `test_input` | object | 测试输入参数：num_prompts, max_out_len, batch_size, request_rate 等 |
| `target` | object | 目标阈值配置 |
| `target.baseline` | number | 基准值，通常为 1 |
| `target.threshold` | number | 阈值，如 0.97 表示达到基准值的 97% 即为 pass |
| `pass_fail` | string | 单个任务的 pass/fail 结果 |

### Pass/Fail 判定规则

- 每个 task 有自己的 `pass_fail` 字段，根据 metrics 是否达到 target 阈值自动判定
- **总体 pass_fail** = 所有 task 都 pass 才算 pass，否则为 fail
- 系统会自动计算总体 pass_fail，无需手动指定

### 其他字段说明

| 字段 | 说明 |
|------|------|
| `test_input.num_prompts` | 提示词数量 |
| `test_input.max_out_len` | 最大输出长度 |
| `test_input.batch_size` | 批次大小 |
| `test_input.request_rate` | 请求速率（可选） |
| `metrics.Prefill_Token_Throughput` | Prefill 阶段 token 吞吐量 |
| `metrics.Input_Token_Throughput` | 输入 token 吞吐量 |
| `metrics.Output_Token_Throughput` | 输出 token 吞吐量 |
| `metrics.Total_Token_Throughput` | 总 token 吞吐量 |
| `metrics.accuracy` | 准确率（如 GSM8K、MMLU 等基准测试） |
