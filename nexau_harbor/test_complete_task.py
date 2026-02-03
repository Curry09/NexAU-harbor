#!/usr/bin/env python3
"""
测试 CompleteTaskMiddleware 与 NexAU Agent 集成
"""

import sys
import os
import json

sys.path.insert(0, "/Users/linjiahang/Desktop/terminal_bench/NexAU-harbor")

from nexau.archs.config.config_loader import load_agent_config
from nexau.archs.tracer.adapters.in_memory import InMemoryTracer

CONFIG_PATH = "/Users/linjiahang/Desktop/terminal_bench/NexAU-harbor/code_agent_gemini_cli/code_agent_gemini_cli.yaml"
LOG_DIR = "/tmp/nexau_test"

os.makedirs(LOG_DIR, exist_ok=True)

print("加载 agent 配置...")
agent = load_agent_config(CONFIG_PATH)

query = "使用搜索工具，计算 2的十次方等于多少"
print(f"任务: {query}")
print("-" * 50)

result = agent.run(query, context={
    "environment_context": "你正在一个名为 NexAU 的终端环境中工作，这个环境是一个基于终端的 AI 助手，你可以使用它来完成各种任务。"
})

for tracer in agent.config.tracers:
    if isinstance(tracer, InMemoryTracer):
        with open(f"{LOG_DIR}/nexau_trace.json", "w") as f:
            json.dump(tracer.dump_traces(), f, indent=2, ensure_ascii=False)
        break

print("-" * 50)
print("完成!")
