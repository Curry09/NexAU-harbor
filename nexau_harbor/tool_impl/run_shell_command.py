# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
run_shell_command tool - Executes shell commands.

Based on gemini-cli's shell.ts implementation.
"""

import json
import os
import platform
import subprocess
import threading
from typing import Any


# Default timeout in seconds
DEFAULT_TIMEOUT = 300  # 5 minutes


def run_shell_command(
    command: str,
    description: str | None = None,
    dir_path: str | None = None,
    is_background: bool = False,
) -> str:
    """
    Executes a given shell command.
    
    On Unix-like systems, runs as `bash -c <command>`.
    On Windows, runs as `powershell.exe -NoProfile -Command <command>`.
    
    Args:
        command: The command to execute
        description: Brief description of the command (for user)
        dir_path: Directory to run the command in (optional)
        is_background: Whether to run in background (optional)
        
    Returns:
        JSON string with command output and status
    """
    try:
        # Validate command
        if not command or not command.strip():
            return json.dumps({
                "error": "Command cannot be empty.",
                "type": "INVALID_COMMAND",
            })
        
        # Determine working directory
        if dir_path:
            cwd = os.path.abspath(dir_path)
            if not os.path.exists(cwd):
                return json.dumps({
                    "error": f"Directory does not exist: {dir_path}",
                    "type": "DIRECTORY_NOT_FOUND",
                })
            if not os.path.isdir(cwd):
                return json.dumps({
                    "error": f"Path is not a directory: {dir_path}",
                    "type": "NOT_A_DIRECTORY",
                })
        else:
            cwd = os.getcwd()
        
        # Determine shell based on platform
        is_windows = platform.system() == "Windows"
        
        if is_windows:
            shell_cmd = ["powershell.exe", "-NoProfile", "-Command", command]
        else:
            shell_cmd = ["bash", "-c", command]
        
        # Handle background execution
        if is_background:
            # Start process in background
            process = subprocess.Popen(
                shell_cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            
            return json.dumps({
                "success": True,
                "background": True,
                "pid": process.pid,
                "message": f"Command moved to background (PID: {process.pid}).",
                "command": command,
                "cwd": cwd,
            })
        
        # Run command synchronously
        try:
            result = subprocess.run(
                shell_cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT,
            )
            
            output_parts = []
            
            # Combined output
            combined_output = ""
            if result.stdout:
                combined_output += result.stdout
            if result.stderr:
                if combined_output:
                    combined_output += "\n"
                combined_output += result.stderr
            
            output_parts.append(f"Output: {combined_output if combined_output.strip() else '(empty)'}")
            
            if result.returncode != 0:
                output_parts.append(f"Exit Code: {result.returncode}")
            
            response: dict[str, Any] = {
                "success": result.returncode == 0,
                "output": combined_output if combined_output.strip() else "(empty)",
                "exit_code": result.returncode,
                "command": command,
                "cwd": cwd,
            }
            
            if description:
                response["description"] = description
            
            return json.dumps(response, ensure_ascii=False)
            
        except subprocess.TimeoutExpired as e:
            # Handle timeout
            output = ""
            if e.stdout:
                output = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else e.stdout
            
            return json.dumps({
                "error": f"Command timed out after {DEFAULT_TIMEOUT} seconds.",
                "type": "TIMEOUT",
                "partial_output": output if output else "(none)",
                "command": command,
            })
            
    except FileNotFoundError as e:
        shell_name = "powershell.exe" if platform.system() == "Windows" else "bash"
        return json.dumps({
            "error": f"Shell not found: {shell_name}. Error: {str(e)}",
            "type": "SHELL_NOT_FOUND",
        })
    except PermissionError:
        return json.dumps({
            "error": f"Permission denied executing command in: {cwd}",
            "type": "PERMISSION_DENIED",
        })
    except Exception as e:
        return json.dumps({
            "error": f"Error executing command: {str(e)}",
            "type": "EXECUTION_ERROR",
        })
