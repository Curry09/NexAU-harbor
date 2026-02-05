# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
run_shell_command tool (shell) - Executes shell commands.

Based on gemini-cli's shell.ts implementation.
Supports foreground and background execution, timeout handling, and process management.
"""

import os
import platform
import signal
import subprocess
import threading
import time
from typing import Any, Callable


# Configuration constants
DEFAULT_TIMEOUT_MS = 300000  # 5 minutes default timeout
OUTPUT_UPDATE_INTERVAL_MS = 1000
BACKGROUND_DELAY_MS = 200


def _format_bytes(num_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f}TB"


def run_shell_command(
    command: str,
    description: str | None = None,
    dir_path: str | None = None,
    is_background: bool = False,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    update_output: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Executes a shell command.
    
    On Unix/Linux/macOS: Executes as `bash -c <command>`
    On Windows: Executes as `powershell.exe -NoProfile -Command <command>`
    
    The following information is returned:
    - Output: Combined stdout/stderr. Can be `(empty)` or partial on error.
    - Exit Code: Only included if non-zero (command failed).
    - Error: Only included if a process-level error occurred.
    - Signal: Only included if process was terminated by a signal.
    - Background PIDs: Only included if background processes were started.
    - Process Group PGID: Only included if available.
    
    Args:
        command: The exact command to execute
        description: Brief description of the command for the user
        dir_path: Directory to run the command in (optional)
        is_background: Whether to run in background
        timeout_ms: Timeout in milliseconds (0 for no timeout)
        update_output: Callback for streaming output updates
        
    Returns:
        Dict with llmContent and returnDisplay matching gemini-cli format
    """
    try:
        # Validate command
        if not command or not command.strip():
            return {
                "llmContent": "Command cannot be empty.",
                "returnDisplay": "Error: Empty command.",
                "error": {
                    "message": "Command cannot be empty.",
                    "type": "INVALID_COMMAND",
                },
            }
        
        # Determine working directory
        if dir_path:
            cwd = os.path.abspath(dir_path)
            if not os.path.exists(cwd):
                error_msg = f"Directory not found: {dir_path}"
                return {
                    "llmContent": error_msg,
                    "returnDisplay": "Error: Directory not found.",
                    "error": {
                        "message": error_msg,
                        "type": "DIRECTORY_NOT_FOUND",
                    },
                }
            if not os.path.isdir(cwd):
                error_msg = f"Path is not a directory: {dir_path}"
                return {
                    "llmContent": error_msg,
                    "returnDisplay": "Error: Path is not a directory.",
                    "error": {
                        "message": error_msg,
                        "type": "NOT_A_DIRECTORY",
                    },
                }
        else:
            cwd = os.getcwd()
        
        # Determine shell and command format based on platform
        is_windows = platform.system() == "Windows"
        
        if is_windows:
            shell_cmd = ["powershell.exe", "-NoProfile", "-Command", command]
        else:
            shell_cmd = ["bash", "-c", command]
        
        # Build description for display
        cmd_description = command
        if dir_path:
            cmd_description += f" [in {dir_path}]"
        else:
            cmd_description += f" [current working directory {cwd}]"
        if description:
            cmd_description += f" ({description.replace(chr(10), ' ')})"
        if is_background:
            cmd_description += " [background]"
        
        # Execute command
        output = ""
        exit_code = None
        error_message = None
        signal_name = None
        pid = None
        backgrounded = False
        aborted = False
        timeout_triggered = False
        
        timeout_sec = timeout_ms / 1000.0 if timeout_ms > 0 else None
        
        try:
            if is_background:
                # Start process in background
                if is_windows:
                    process = subprocess.Popen(
                        shell_cmd,
                        cwd=cwd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    )
                else:
                    process = subprocess.Popen(
                        shell_cmd,
                        cwd=cwd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                
                pid = process.pid
                backgrounded = True
                
                # Wait briefly to check for immediate errors
                time.sleep(BACKGROUND_DELAY_MS / 1000.0)
                
                # Check if process is still running
                poll_result = process.poll()
                if poll_result is not None:
                    # Process exited immediately - likely an error
                    output, _ = process.communicate()
                    if isinstance(output, bytes):
                        output = output.decode("utf-8", errors="replace")
                    exit_code = poll_result
                    backgrounded = False
                else:
                    # Process is running in background
                    llm_content = f"Command moved to background (PID: {pid}). Output hidden."
                    return {
                        "llmContent": llm_content,
                        "returnDisplay": llm_content,
                        "data": {
                            "pid": pid,
                            "command": command,
                            "backgrounded": True,
                        },
                    }
            else:
                # Foreground execution with streaming output
                process = subprocess.Popen(
                    shell_cmd,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=not is_windows,
                )
                
                pid = process.pid
                output_chunks = []
                last_update_time = time.time()
                
                def read_output():
                    nonlocal output_chunks, last_update_time
                    while True:
                        chunk = process.stdout.read(4096)
                        if not chunk:
                            break
                        
                        try:
                            decoded = chunk.decode("utf-8", errors="replace")
                        except Exception:
                            decoded = f"[Binary data: {len(chunk)} bytes]"
                        
                        output_chunks.append(decoded)
                        
                        # Update output periodically
                        current_time = time.time()
                        if update_output and (current_time - last_update_time) > (OUTPUT_UPDATE_INTERVAL_MS / 1000.0):
                            update_output("".join(output_chunks))
                            last_update_time = current_time
                
                output_thread = threading.Thread(target=read_output)
                output_thread.start()
                
                try:
                    process.wait(timeout=timeout_sec)
                except subprocess.TimeoutExpired:
                    timeout_triggered = True
                    aborted = True
                    # Kill the process group
                    try:
                        if is_windows:
                            process.kill()
                        else:
                            os.killpg(os.getpgid(pid), signal.SIGTERM)
                            time.sleep(0.5)
                            try:
                                os.killpg(os.getpgid(pid), signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    except (ProcessLookupError, PermissionError):
                        pass
                
                output_thread.join(timeout=5.0)
                output = "".join(output_chunks)
                exit_code = process.returncode
                
        except FileNotFoundError:
            error_message = f"Command not found: {shell_cmd[0]}"
        except PermissionError:
            error_message = f"Permission denied executing command"
        except Exception as e:
            error_message = str(e)
        
        # Build result
        llm_parts = []
        
        if aborted:
            if timeout_triggered:
                timeout_minutes = (timeout_ms / 60000)
                timeout_msg = f"Command was automatically cancelled because it exceeded the timeout of {timeout_minutes:.1f} minutes without output."
                llm_parts.append(timeout_msg)
            else:
                llm_parts.append("Command was cancelled by user before it could complete.")
            
            if output and output.strip():
                llm_parts.append(f"Below is the output before it was cancelled:\n{output}")
            else:
                llm_parts.append("There was no output before it was cancelled.")
        else:
            llm_parts.append(f"Output: {output if output else '(empty)'}")
            
            if error_message:
                llm_parts.append(f"Error: {error_message}")
            
            if exit_code is not None and exit_code != 0:
                llm_parts.append(f"Exit Code: {exit_code}")
            
            if signal_name:
                llm_parts.append(f"Signal: {signal_name}")
            
            if pid:
                llm_parts.append(f"Process Group PGID: {pid}")
        
        llm_content = "\n".join(llm_parts)
        
        # Build return display
        if backgrounded:
            return_display = f"Command moved to background (PID: {pid}). Output hidden."
        elif output and output.strip():
            return_display = output
        elif aborted:
            if timeout_triggered:
                return_display = f"Command timed out after {timeout_ms / 60000:.1f} minutes."
            else:
                return_display = "Command cancelled by user."
        elif signal_name:
            return_display = f"Command terminated by signal: {signal_name}"
        elif error_message:
            return_display = f"Command failed: {error_message}"
        elif exit_code is not None and exit_code != 0:
            return_display = f"Command exited with code: {exit_code}"
        else:
            return_display = "(empty)"
        
        result = {
            "llmContent": llm_content,
            "returnDisplay": return_display,
        }
        
        if error_message:
            result["error"] = {
                "message": error_message,
                "type": "SHELL_EXECUTE_ERROR",
            }
        
        if backgrounded:
            result["data"] = {
                "pid": pid,
                "command": command,
                "backgrounded": True,
            }
        
        return result
        
    except Exception as e:
        error_msg = f"Error executing shell command: {str(e)}"
        return {
            "llmContent": error_msg,
            "returnDisplay": error_msg,
            "error": {
                "message": error_msg,
                "type": "SHELL_EXECUTE_ERROR",
            },
        }
