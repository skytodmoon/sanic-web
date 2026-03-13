const systemInstructions = `你正在操作 Aix-DB 智能数据问答平台。该平台有两种页面状态：默认首页（提问页）和对话页（结果页）。提交问题后会从首页跳转到对话页，在对话页可以继续追问。

## 默认首页（提问页）
页面中央有一个白色输入卡片（class="input-card"），包含:
- 文本输入框: textarea 元素
- 底部左侧（class="left-actions"）: 4个模式按钮（class="inner-chip"）
  - 智能问答 / 数据问答 / 表格问答 / 深度问数
- 底部右侧: 发送按钮 <button aria-label="发送" class="send-btn-circle">

## 对话页（结果页）
提交后自动跳转到此页面。页面结构:
- 上方: 对话记录区域，包含多轮用户提问和AI回复
  - 用户消息: 右侧蓝色背景气泡，显示提问文字
  - AI回复: 左侧区域，包含 class="markdown-wrapper" 的文字内容和可能的图表/表格
- 下方: 追问输入区域（class="bottom-input-container"），结构与首页类似:
  - textarea 输入框（class="custom-chat-input"）
  - 发送按钮 <button aria-label="发送" class="send-btn-circle">

## 数据问答完整流程
1. 点击"数据问答"按钮（class="inner-chip"）
2. 从弹出的数据源列表中选择一个数据源
3. 在 textarea 中输入问题
4. 点击发送按钮（aria-label="发送"）
5. 等待页面跳转到对话页，AI开始流式返回结果
6. **等待结果完成** — 判断标志:
   - class="star-spinner" 动画消失
   - "正在思考中..." 文字消失
   - 页面底部的追问输入框（class="bottom-input-container"）已出现
7. **获取最新结果**: 读取页面中**最后一个** class="markdown-wrapper" 的内容（即最新的AI回复）
8. 总结整理数据: 提取SQL语句、数据表格、分析结论

## 追问流程（在对话页继续提问）
1. 在底部的追问输入框（class="custom-chat-input" 的 textarea）中输入新问题
2. 点击底部的发送按钮（aria-label="发送"）
3. 等待新一轮AI回复完成（同上述等待标志）
4. 读取**最后一个** class="markdown-wrapper" 获取最新结果

## 重要注意事项
- 所有发送按钮均为 <button> 元素，aria-label="发送"
- 发送按钮在输入框无内容时处于 disabled 状态
- 对话页可能有多轮对话，最新的AI回复是**最后一个** class="markdown-wrapper" 元素
- 必须等待AI回复完全结束再获取结果（无加载动画、内容稳定）
- 数据问答的结果通常包含: 文字分析 + SQL语句 + 数据表格/图表`

function getPageInstructions(url: string): string | undefined {
  if (url.includes('/chat')) {
    return `当前页面是 Aix-DB 的聊天/问答页面。

## 元素定位

### 默认首页（中央有大 "Aix" Logo 时）
- **模式按钮**: class="inner-chip"，文字为"智能问答"/"数据问答"/"表格问答"/"深度问数"
- **已选模式**: class="mode-pill"，显示当前模式和数据源
- **输入框**: class="input-card" 内的 textarea
- **发送按钮**: <button aria-label="发送" class="send-btn-circle">

### 对话页（有对话记录时）
- **对话记录**: 多个 class="mb-4" 的 div，按时间顺序排列
  - 用户消息在右侧（背景色 #f5f7ff）
  - AI回复在左侧，内容在 class="markdown-wrapper" 中
- **最新AI回复**: 页面中**最后一个** class="markdown-wrapper" 元素
- **加载中标志**: class="star-spinner" 可见 或 "正在思考中..." 文字可见
- **加载完成标志**: 无星星动画，底部追问输入框可见
- **追问输入框**: class="bottom-input-container" 内的 textarea（class="custom-chat-input"）
- **追问发送按钮**: class="bottom-input-container" 内的 <button aria-label="发送">

### 获取最新结果的步骤
1. 确认加载已完成（无动画、底部输入框可见）
2. 找到页面中**最后一个** class="markdown-wrapper" 元素
3. 读取其中所有文本内容（包含分析文字和SQL）
4. 如果下方有 <table> 元素，也读取表格数据
5. 将结果总结为: SQL语句 + 数据要点 + 关键发现`
  }
  return undefined
}

export const pageAgentInstructions = {
  system: systemInstructions,
  getPageInstructions,
}
