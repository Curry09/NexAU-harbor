#!/usr/bin/env python3
"""
NexAU Harbor CLI

使用方法:
    nexau-harbor run --config config.yaml
"""

import argparse
import sys
from nexau.archs.config.config_loader import load_agent_config
from nexau.archs.tracer.adapters.in_memory import InMemoryTracer
import json
def cmd_run(args):
    """执行 agent 任务"""
    print(f"配置文件: {args.config_path}")
    print(f"任务: {args.query}")
    print("-" * 50)
    
    agent = load_agent_config(args.config_path)
    result = agent.run(args.query)
    for tracer in agent.config.tracers:
        if isinstance(tracer, InMemoryTracer):
            with open(args.log_dir_path+"/nexau_in_memory_tracer.json", "w") as f:
                json.dump(tracer.dump_traces(), f, indent=2, ensure_ascii=False)
            break
    print("Agent 运行完成!")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="nexau-harbor",
        description="NexAU Agent CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行 agent 任务")
    run_parser.add_argument("--config_path", required=True, help="配置文件路径")
    run_parser.add_argument("--query", required=True, help="任务描述")
    run_parser.add_argument("--log_dir_path", required=True, help="结果保存路径")

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
