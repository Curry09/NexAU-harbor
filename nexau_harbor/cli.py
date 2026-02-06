#!/usr/bin/env python3
"""
NexAU Harbor CLI

使用方法:
    nexau-harbor run --config config.yaml
"""

import argparse
import sys
import os
from dataclasses import dataclass, field
from typing import Optional
from nexau.archs.config.config_loader import load_agent_config
from nexau.archs.tracer.adapters.in_memory import InMemoryTracer
import json


# Constants matching gemini-cli
MAX_ITEMS = 200
TRUNCATION_INDICATOR = '...'
DEFAULT_IGNORED_FOLDERS = {'node_modules', '.git', 'dist', '__pycache__'}


@dataclass
class FullFolderInfo:
    """Represents the full information about a folder and its contents."""
    name: str
    path: str
    files: list = field(default_factory=list)
    sub_folders: list = field(default_factory=list)
    total_children: int = 0
    total_files: int = 0
    is_ignored: bool = False
    has_more_files: bool = False
    has_more_subfolders: bool = False


def read_full_structure(
    root_path: str,
    max_items: int,
    ignored_folders: set,
) -> Optional[FullFolderInfo]:
    """
    Reads the directory structure using BFS, respecting maxItems.
    Matches gemini-cli's readFullStructure function.
    """
    root_name = os.path.basename(root_path)
    root_node = FullFolderInfo(name=root_name, path=root_path)
    
    queue = [{'folder_info': root_node, 'current_path': root_path}]
    current_item_count = 0
    processed_paths = set()
    
    while queue:
        item = queue.pop(0)  # BFS: pop from front
        folder_info = item['folder_info']
        current_path = item['current_path']
        
        if current_path in processed_paths:
            continue
        processed_paths.add(current_path)
        
        if current_item_count >= max_items:
            continue
        
        try:
            raw_entries = os.listdir(current_path)
            entries = sorted(raw_entries)
        except (PermissionError, FileNotFoundError) as e:
            if current_path == root_path:
                return None
            continue
        
        files_in_current_dir = []
        sub_folders_in_current_dir = []
        
        # Process files first in the current directory
        for entry in entries:
            full_path = os.path.join(current_path, entry)
            if os.path.isfile(full_path):
                if current_item_count >= max_items:
                    folder_info.has_more_files = True
                    break
                files_in_current_dir.append(entry)
                current_item_count += 1
                folder_info.total_files += 1
                folder_info.total_children += 1
        
        folder_info.files = files_in_current_dir
        
        # Then process directories and queue them
        for entry in entries:
            full_path = os.path.join(current_path, entry)
            if os.path.isdir(full_path):
                if current_item_count >= max_items:
                    folder_info.has_more_subfolders = True
                    break
                
                sub_folder_name = entry
                sub_folder_path = full_path
                
                if sub_folder_name in ignored_folders:
                    ignored_sub_folder = FullFolderInfo(
                        name=sub_folder_name,
                        path=sub_folder_path,
                        is_ignored=True,
                    )
                    sub_folders_in_current_dir.append(ignored_sub_folder)
                    current_item_count += 1
                    folder_info.total_children += 1
                    continue
                
                sub_folder_node = FullFolderInfo(
                    name=sub_folder_name,
                    path=sub_folder_path,
                )
                sub_folders_in_current_dir.append(sub_folder_node)
                current_item_count += 1
                folder_info.total_children += 1
                
                # Add to queue for processing its children later
                queue.append({'folder_info': sub_folder_node, 'current_path': sub_folder_path})
        
        folder_info.sub_folders = sub_folders_in_current_dir
    
    return root_node


def format_structure(
    node: FullFolderInfo,
    current_indent: str,
    is_last_child_of_parent: bool,
    is_processing_root_node: bool,
    builder: list,
) -> None:
    """
    Formats the folder structure into a string representation.
    Matches gemini-cli's formatStructure function.
    """
    connector = '└───' if is_last_child_of_parent else '├───'
    
    # The root node is not printed with a connector line itself
    # Ignored root nodes ARE printed with a connector
    if not is_processing_root_node or node.is_ignored:
        suffix = TRUNCATION_INDICATOR if node.is_ignored else ''
        builder.append(f"{current_indent}{connector}{node.name}/{suffix}")
    
    # Determine the indent for the children of this node
    if is_processing_root_node:
        indent_for_children = ''
    else:
        indent_for_children = current_indent + ('    ' if is_last_child_of_parent else '│   ')
    
    # Render files of the current node
    file_count = len(node.files)
    for i, file_name in enumerate(node.files):
        is_last_file_among_siblings = (
            i == file_count - 1 and
            len(node.sub_folders) == 0 and
            not node.has_more_subfolders
        )
        file_connector = '└───' if is_last_file_among_siblings else '├───'
        builder.append(f"{indent_for_children}{file_connector}{file_name}")
    
    if node.has_more_files:
        is_last_indicator_among_siblings = (
            len(node.sub_folders) == 0 and not node.has_more_subfolders
        )
        file_connector = '└───' if is_last_indicator_among_siblings else '├───'
        builder.append(f"{indent_for_children}{file_connector}{TRUNCATION_INDICATOR}")
    
    # Render subfolders of the current node
    sub_folder_count = len(node.sub_folders)
    for i, sub_folder in enumerate(node.sub_folders):
        is_last_subfolder_among_siblings = (
            i == sub_folder_count - 1 and not node.has_more_subfolders
        )
        format_structure(
            sub_folder,
            indent_for_children,
            is_last_subfolder_among_siblings,
            False,
            builder,
        )
    
    if node.has_more_subfolders:
        builder.append(f"{indent_for_children}└───{TRUNCATION_INDICATOR}")


def is_truncated(node: FullFolderInfo) -> bool:
    """Check if any part of the tree is truncated."""
    if node.has_more_files or node.has_more_subfolders or node.is_ignored:
        return True
    for sub in node.sub_folders:
        if is_truncated(sub):
            return True
    return False


def get_folder_structure(
    directory: str,
    max_items: int = MAX_ITEMS,
    ignored_folders: set = None,
) -> str:
    """
    Generates a string representation of a directory's structure.
    Matches gemini-cli's getFolderStructure function exactly.
    
    Args:
        directory: The absolute or relative path to the directory.
        max_items: Maximum number of files and folders combined to display.
        ignored_folders: Set of folder names to ignore completely.
        
    Returns:
        The formatted folder structure string.
    """
    if ignored_folders is None:
        ignored_folders = DEFAULT_IGNORED_FOLDERS
    
    resolved_path = os.path.abspath(directory)
    
    try:
        # 1. Read the structure using BFS, respecting maxItems
        structure_root = read_full_structure(resolved_path, max_items, ignored_folders)
        
        if not structure_root:
            return f'Error: Could not read directory "{resolved_path}". Check path and permissions.'
        
        # 2. Format the structure into a string
        structure_lines = []
        format_structure(structure_root, '', True, True, structure_lines)
        
        # 3. Build the final output string
        summary = f"Showing up to {max_items} items (files + folders)."
        
        if is_truncated(structure_root):
            summary += f" Folders or files indicated with {TRUNCATION_INDICATOR} contain more items not shown, were ignored, or the display limit ({max_items} items) was reached."
        
        return f"{summary}\n\n{resolved_path}/\n{chr(10).join(structure_lines)}"
    
    except Exception as e:
        return f'Error processing directory "{resolved_path}": {str(e)}'


def get_directory_context_string(working_dir: str) -> str:
    """
    Generates a string describing the current workspace directory and its structure.
    Matches gemini-cli's getDirectoryContextString function exactly.
    
    Args:
        working_dir: The working directory path.
        
    Returns:
        The directory context string.
    """
    folder_structure = get_folder_structure(working_dir)
    
    return f"""I'm currently working in the directory: {working_dir}
Here is the folder structure of the current working directories:

{folder_structure}"""


def cmd_run(args):
    """执行 agent 任务"""
    print(f"配置文件: {args.config_path}")
    print(f"任务: {args.query}")
    print("-" * 50)
    os.makedirs(args.log_dir_path, exist_ok=True)
    # 动态生成环境上下文
    working_dir = args.working_dir
    import platform
    from datetime import datetime
    import locale

    # Format today's date per user's locale
    try:
        loc = locale.getdefaultlocale()[0]
    except Exception:
        loc = 'en_US'
    now = datetime.now()
    try:
        formatted_today = now.strftime("%A, %B %d, %Y")
    except Exception:
        formatted_today = now.strftime("%Y-%m-%d")

    # Substitute the actual project temp directory if available; else, use a placeholder
    import random
    import string
    def random_hex(n: int) -> str:
        return ''.join(random.choices('0123456789abcdef', k=n))
    project_tmp_dir = f"/root/.gemini/tmp/{random_hex(64)}"
    os_type = platform.system().lower()

    folder_structure = get_folder_structure(working_dir)

    environment_context = (
        "This is the Gemini CLI. We are setting up the context for our chat.\n"
        f"Today's date is {formatted_today} (formatted according to the user's locale).\n"
        f"My operating system is: {os_type}\n"
        f"The project's temporary directory is: {project_tmp_dir}\n, you must first mkdir it before using it"
        f"I'm currently working in the directory: {working_dir}\n"
        "Here is the folder structure of the current working directories:\n\n"
        f"Showing up to {MAX_ITEMS} items (files + folders).\n\n"
        f"{folder_structure}\n\n"
        "Reminder: Do not return an empty response when a tool call is required.\n\n"
        "My setup is complete. I will provide my first command in the next turn."
    )
    agent = load_agent_config(args.config_path)
    result = agent.run(
        message=args.query,
        context={
            "environment_context": environment_context,
        }
    )
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
    run_parser.add_argument("--working_dir", required=False, help="工作目录", default=os.getcwd())

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
