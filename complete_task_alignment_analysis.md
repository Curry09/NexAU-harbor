# Gemini-CLI vs NexAU complete_task 对齐分析

## 🔍 关键差异发现

### 1. **执行流程差异**

#### Gemini-CLI (`local-executor.ts`)
```typescript
// executeTurn() 中：
if (functionCalls.length === 0) {
  // 立即停止，返回 ERROR_NO_COMPLETE_TASK_CALL
  return { status: 'stop', terminateReason: ERROR_NO_COMPLETE_TASK_CALL }
}

// 处理工具调用
const { taskCompleted } = await processFunctionCalls(...)
if (taskCompleted) {
  return { status: 'stop', terminateReason: GOAL, finalResult }
}

// 继续循环
return { status: 'continue', nextMessage }
```

**特点**：
- ✅ 无工具调用 → **立即停止** → 进入 recovery
- ✅ 调用 complete_task → **立即停止** → GOAL
- ✅ Recovery 机制：`executeFinalWarningTurn()` 给最后一次机会

#### NexAU (`executor.py`)
```python
# _process_xml_calls() 中：
if not parsed_response or not parsed_response.has_calls():
    if force_continue:
        return ..., False, None, ...  # 继续
    else:
        return ..., True, None, ...   # 停止

# 执行工具调用
processed_response, should_stop, ... = _execute_parsed_calls(...)
```

**特点**：
- ⚠️ 无工具调用 → 检查 `force_continue` → 可能继续
- ⚠️ 调用 complete_task → 需要工具执行后返回结果
- ❌ **没有 recovery 机制**

### 2. **complete_task 处理差异**

#### Gemini-CLI
```typescript
// processFunctionCalls() 中：
if (toolName === TASK_COMPLETE_TOOL_NAME) {
  // 同步处理，不执行工具
  taskCompleted = true
  submittedOutput = args['result']
  // 立即返回，不执行其他工具
  continue
}
```

**特点**：
- ✅ `complete_task` 被**特殊处理**，不实际执行工具
- ✅ 立即设置 `taskCompleted = true`
- ✅ 其他工具调用被忽略

#### NexAU
```python
# complete_task_hook.py 中：
if complete_task_call:
    parsed.tool_calls = []  # 清空其他工具
    return HookResult.with_modifications(parsed_response=parsed)
```

**问题**：
- ⚠️ `complete_task` 仍然会**实际执行**工具
- ⚠️ 清空了 `tool_calls`，但工具可能已经执行
- ❌ 没有立即停止机制

### 3. **Recovery 机制差异**

#### Gemini-CLI
```typescript
// run() 主循环中：
if (terminateReason 是可恢复的) {
  const recoveryResult = await executeFinalWarningTurn(...)
  if (recoveryResult !== null) {
    terminateReason = GOAL  // 恢复成功
  }
}
```

**特点**：
- ✅ 统一的 recovery 块
- ✅ 支持 TIMEOUT, MAX_TURNS, ERROR_NO_COMPLETE_TASK_CALL
- ✅ 60秒 grace period

#### NexAU
```python
# complete_task_hook.py 中：
if self.no_tool_call_count >= 2:
    return HookResult.no_changes()  # 退出
```

**问题**：
- ❌ **没有 recovery 机制**
- ❌ 直接退出，不给模型最后一次机会
- ❌ 不区分可恢复和不可恢复的错误

### 4. **agent_response 处理差异**

#### Gemini-CLI
- 使用 `finalResult` 字段直接返回结果
- 在 `executeTurn()` 中设置并返回

#### NexAU
```python
# hooks.py run_after_model() 中：
return current_parsed, current_messages, force_continue
# ❌ 不返回 agent_response！
```

**关键问题**：
- ❌ `after_model` hook 中的 `agent_response` **被忽略**
- ❌ `run_after_model()` 只返回 3 个值，不包含 `agent_response`
- ❌ 无法通过 hook 直接设置最终响应

## 🚨 未对齐的关键点

### 1. **complete_task 应该立即停止，不执行工具**

**当前实现**：
```python
if complete_task_call:
    parsed.tool_calls = []  # 只是清空，但工具可能已执行
    return HookResult.with_modifications(parsed_response=parsed)
```

**应该**：
- 在 `before_tool` 中拦截 `complete_task`，直接返回结果
- 或者修改 executor 逻辑，特殊处理 `complete_task`

### 2. **需要 recovery 机制**

**当前实现**：
- 连续 2 轮无工具调用 → 直接退出

**应该**：
- 检测到协议违规 → 进入 grace period
- 发送警告消息
- 给模型最后一次机会调用 `complete_task`

### 3. **agent_response 无法通过 after_model 设置**

**当前限制**：
- `run_after_model()` 不返回 `agent_response`
- 只能在 `after_agent` hook 中修改

**解决方案**：
- 在 `after_tool` 中检测 `complete_task` 执行成功
- 设置一个标志，在 executor 主循环中检查
- 或者修改 executor 支持从 hook 返回 `agent_response`

## 📋 修复建议

### 优先级 1：complete_task 立即停止
1. 在 `before_tool` 中拦截 `complete_task`
2. 直接返回结果，不执行工具
3. 设置标志让 executor 停止

### 优先级 2：实现 recovery 机制
1. 检测协议违规（无工具调用）
2. 进入 grace period（1-2 轮）
3. 注入警告消息
4. 如果仍无 `complete_task`，再退出

### 优先级 3：支持 agent_response
1. 修改 `run_after_model()` 返回 `agent_response`
2. 或者在 executor 中检查 hook 设置的标志

