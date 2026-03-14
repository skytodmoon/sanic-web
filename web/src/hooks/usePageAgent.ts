import { PageAgent } from 'page-agent'
import { ref, shallowRef } from 'vue'
import { fetch_model_list } from '@/api/aimodel'
import { pageAgentInstructions } from './pageAgentInstructions'

const BRIDGE_VERSION = '2.1.0'

interface TaskResult {
  status: 'idle' | 'running' | 'done' | 'error'
  result?: { success: boolean, data: string, history?: unknown[] }
  error?: string
}

declare global {
  interface Window {
    __aixPageAgent?: {
      version: string
      execute: (command: string) => Promise<{ success: boolean, data: string }>
      startTask: (task: string) => { success: boolean, data: string }
      getTaskResult: () => TaskResult
      isReady: () => boolean
      getStatus: () => string
      isInitialized?: () => boolean
    }
  }
}

const PAGE_AGENT_MODEL = 'qwen3.5-plus'

const agentInstance = shallowRef<PageAgent | null>(null)
const agentReady = ref(false)
let lastTaskResult: TaskResult = { status: 'idle' }

/**
 * 通过 Panel 原生输入框提交任务。
 * 找到 Panel DOM 中的 input，填入文本后模拟 Enter 触发原生 submitTask 流程。
 * 返回 true 表示成功走了原生路径，false 表示需要 fallback。
 */
function submitViaPanel(agent: PageAgent, command: string): boolean {
  const wrapper = agent.panel.wrapper
  if (!wrapper) {
    console.log(`[PageAgent v${BRIDGE_VERSION}] submitViaPanel: no wrapper`)
    return false
  }

  const panelEl = document.getElementById('page-agent-runtime_agent-panel')
  const root = panelEl || wrapper

  const inputWrapper = root.querySelector('[class*="inputSectionWrapper"]') as HTMLElement | null
  const inputEl = root.querySelector('input[type="text"][maxlength="200"]') as HTMLInputElement | null

  console.log(`[PageAgent v${BRIDGE_VERSION}] submitViaPanel: wrapper=${!!inputWrapper}, input=${!!inputEl}`)

  if (!inputWrapper || !inputEl) return false

  // 确保输入区域可见（移除 hidden class）
  inputWrapper.className = inputWrapper.className
    .split(' ')
    .filter(c => !c.includes('hidden'))
    .join(' ')

  // 设置输入值并触发原生 Enter 提交
  inputEl.value = command
  inputEl.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter',
    code: 'Enter',
    keyCode: 13,
    which: 13,
    bubbles: true,
    cancelable: true,
  }))

  console.log(`[PageAgent v${BRIDGE_VERSION}] submitViaPanel: Enter dispatched`)
  return true
}

function runTask(agent: PageAgent, command: string): Promise<unknown> {
  agent.panel.show()
  agent.panel.expand()

  if (submitViaPanel(agent, command)) {
    // 原生路径成功，agent.execute 已由 Panel 的 submitTask 内部调用
    return new Promise<void>((resolve) => {
      const check = () => {
        const s = agent.status
        if (s === 'completed' || s === 'error' || s === 'idle') {
          agent.removeEventListener('statuschange', check)
          resolve()
        }
      }
      agent.addEventListener('statuschange', check)
      // 超时兜底
      setTimeout(() => {
        agent.removeEventListener('statuschange', check)
        resolve()
      }, 120_000)
    })
  }

  console.log(`[PageAgent v${BRIDGE_VERSION}] fallback: direct execute`)
  return agent.execute(command)
}

function exposeBridge() {
  console.log(`[PageAgent bridge v${BRIDGE_VERSION}] exposing`)

  window.__aixPageAgent = {
    version: BRIDGE_VERSION,

    execute: async (command: string) => {
      console.log(`[PageAgent v${BRIDGE_VERSION}] execute:`, command)
      const agent = agentInstance.value
      if (!agent) {
        console.warn('[PageAgent] not initialized')
        return { success: false, data: 'PageAgent not initialized' }
      }
      lastTaskResult = { status: 'running' }
      try {
        await runTask(agent, command)
        const result = lastTaskResult.status === 'done' ? lastTaskResult.result : undefined
        return { success: true, data: result?.data ?? 'Task completed' }
      }
      catch (e: any) {
        lastTaskResult = { status: 'error', error: e?.message ?? String(e) }
        return { success: false, data: e?.message ?? 'Task failed' }
      }
    },

    startTask: (task: string) => {
      console.log(`[PageAgent v${BRIDGE_VERSION}] startTask:`, task)
      const agent = agentInstance.value
      if (!agent) {
        console.warn('[PageAgent] not initialized')
        return { success: false, data: 'PageAgent not initialized' }
      }
      lastTaskResult = { status: 'running' }

      runTask(agent, task)
        .then(() => {
          if (lastTaskResult.status === 'running') {
            lastTaskResult = { status: 'done', result: { success: true, data: 'Task completed' } }
          }
          console.log(`[PageAgent v${BRIDGE_VERSION}] task done`)
        })
        .catch((e: any) => {
          lastTaskResult = { status: 'error', error: e?.message ?? String(e) }
          console.error(`[PageAgent v${BRIDGE_VERSION}] task error:`, e)
        })

      return { success: true, data: 'Task started' }
    },

    getTaskResult: () => lastTaskResult,

    isReady: () => {
      const ready = agentReady.value
      console.log(`[PageAgent v${BRIDGE_VERSION}] isReady:`, ready)
      return ready
    },

    isInitialized: () => agentReady.value,

    getStatus: () => agentInstance.value?.status ?? 'idle',
  }
}

function removeBridge() {
  delete window.__aixPageAgent
}

// ============================================
// 面板定位逻辑：让 page-agent 面板居中于 input-card，宽度为其一半
// ============================================

// 定位清理函数，销毁时调用以移除所有事件监听
let panelPositionCleanup: (() => void) | null = null

/**
 * 重新计算并设置面板位置
 * 根据当前页面（默认首页 / 聊天页 / 登录页）分别定位
 * 默认首页、聊天页：基于可见的 .input-card 居中，宽度为其一半
 * 登录页：基于 .login-card 居中，位置往下调整
 */
function repositionPanel(wrapper: HTMLElement) {
  // ---------- 1. 尝试登录页 ----------
  const loginCard = document.querySelector('.login-container .login-card') as HTMLElement | null
  if (loginCard && loginCard.offsetParent !== null) {
    const loginRect = loginCard.getBoundingClientRect() // 登录卡片位置
    const centerX = loginRect.left + loginRect.width / 2 // 水平中心
    const viewportH = window.innerHeight
    // 登录页：面板在登录卡片下方，间距 20px
    const bottomOffset = viewportH - loginRect.bottom - 20
    wrapper.style.left = `${centerX}px`
    wrapper.style.bottom = `${Math.max(bottomOffset, 8)}px`
    wrapper.style.maxWidth = `${loginRect.width / 2}px` // 宽度为登录卡片的一半
    return
  }

  // ---------- 2. 尝试默认首页 / 聊天页的 .input-card ----------
  const cards = document.querySelectorAll<HTMLElement>('.input-card')
  let foundCard: HTMLElement | null = null
  // 遍历找到当前可见的那个（offsetParent 不为 null 表示可见）
  cards.forEach((c) => {
    if (c.offsetParent !== null) foundCard = c
  })

  // 找不到可见的 input-card 时，降级为内容区居中
  if (!foundCard) {
    const contentEl = document.querySelector('.n-layout-scroll-container') as HTMLElement
      ?? document.querySelector('.n-layout-content') as HTMLElement
    if (!contentEl) return
    const rect = contentEl.getBoundingClientRect()
    wrapper.style.left = `${rect.left + rect.width / 2}px` // 水平居中于内容区
    wrapper.style.bottom = '100px' // 默认距底 100px
    return
  }

  const card: HTMLElement = foundCard
  const cardRect = card.getBoundingClientRect() // 获取 input-card 的位置和尺寸
  const cardCenterX = cardRect.left + cardRect.width / 2 // input-card 的水平中心点
  const viewportH = window.innerHeight // 视口高度

  // 判断当前是默认首页还是聊天页（通过祖先元素判断）
  const isDefaultPage = !!card.closest('.default-page-container')
  let bottomOffset: number
  if (isDefaultPage) {
    // 默认首页：面板在 input-card 下方，距底部较远（输入框在页面中间偏上）
    bottomOffset = viewportH - cardRect.bottom - 240
  }
  else {
    // 聊天页：输入框贴底，面板在 input-card 上方
    bottomOffset = viewportH - cardRect.top - 100
  }

  wrapper.style.left = `${cardCenterX}px` // 水平居中于 input-card
  wrapper.style.bottom = `${Math.max(bottomOffset, 8)}px` // 垂直位置，最小 8px 防止贴底
  wrapper.style.maxWidth = `${cardRect.width / 2}px` // 宽度限制为 input-card 的一半
}

/**
 * 初始化面板定位：监听布局变化，实时更新面板位置
 * 监听 ResizeObserver（容器大小变化）、window resize、scroll、MutationObserver（DOM 增删如 v-if 切换）
 */
function setupPanelPositioning(agent: PageAgent) {
  // 获取面板的 wrapper DOM 元素
  const wrapper = (agent.panel as any).wrapper as HTMLElement | undefined
  if (!wrapper) return

  // 存储所有清理函数，销毁时统一调用
  const cleanups: Array<() => void> = []

  // 封装定位函数
  const doPosition = () => repositionPanel(wrapper)

  // 尝试挂载所有监听器
  const tryAttach = () => {
    // 找到内容区布局元素
    const layoutEl = document.querySelector('.n-layout-content') as HTMLElement
      ?? document.querySelector('.n-layout') as HTMLElement
    if (!layoutEl) return false // 布局元素还没渲染，稍后重试

    doPosition() // 立即执行一次定位

    // 监听内容区大小变化（如侧栏展开/折叠）
    const ro = new ResizeObserver(doPosition)
    ro.observe(layoutEl)
    cleanups.push(() => ro.disconnect())

    // 监听窗口大小变化
    window.addEventListener('resize', doPosition)
    cleanups.push(() => window.removeEventListener('resize', doPosition))

    // 监听滚动容器的滚动事件（input-card 位置可能随滚动变化）
    const scrollEls = document.querySelectorAll('.n-layout-scroll-container')
    scrollEls.forEach((el) => {
      el.addEventListener('scroll', doPosition, { passive: true })
      cleanups.push(() => el.removeEventListener('scroll', doPosition))
    })

    // 监听 DOM 子树变化（v-if 切换默认页/聊天页时 input-card 会增删）
    const mo = new MutationObserver(doPosition)
    mo.observe(layoutEl, { childList: true, subtree: true })
    cleanups.push(() => mo.disconnect())

    return true
  }

  // 如果首次挂载失败（布局元素还没渲染），用 MutationObserver 等待
  if (!tryAttach()) {
    const mo = new MutationObserver(() => {
      if (tryAttach()) mo.disconnect() // 挂载成功后停止观察
    })
    mo.observe(document.body, { childList: true, subtree: true })
    cleanups.push(() => mo.disconnect())
  }

  // 保存清理函数，在 destroyAgent 时调用
  panelPositionCleanup = () => cleanups.forEach(fn => fn())
}

// ============================================
// 对外暴露的 composable
// ============================================
export function usePageAgent() {
  const initAgent = (config: { baseURL: string, apiKey: string }) => {
    if (agentInstance.value) {
      destroyAgent()
    }

    const agent = new PageAgent({
      model: PAGE_AGENT_MODEL,
      baseURL: config.baseURL,
      apiKey: config.apiKey,
      language: 'zh-CN',
      maxSteps: 20,
      instructions: pageAgentInstructions,
      onAfterTask: (_agent, result) => {
        lastTaskResult = { status: result.success ? 'done' : 'error', result }
      },
    })

    agent.panel.show()

    agentInstance.value = agent
    agentReady.value = true
    lastTaskResult = { status: 'idle' }
    exposeBridge()
    console.log(`[PageAgent v${BRIDGE_VERSION}] initialized, model: ${PAGE_AGENT_MODEL}`)
    return agent
  }

  const initFromDefaultModel = async () => {
    try {
      const res = await fetch_model_list(undefined, 1)
      const list = Array.isArray(res?.data) ? res.data : Array.isArray(res) ? res : []
      const defaultModel = list.find((m: any) => m.default_model) || list[0]

      if (!defaultModel) {
        console.warn('[PageAgent] 无可用模型')
        return
      }

      if (!defaultModel.api_domain) {
        console.warn('[PageAgent] 默认模型缺少 api_domain:', defaultModel.name)
        return
      }

      initAgent({
        baseURL: defaultModel.api_domain,
        apiKey: defaultModel.api_key || '',
      })
    }
    catch (e) {
      console.error('[PageAgent] 加载默认模型配置失败:', e)
    }
  }

  const initFromEnv = () => {
    const apiKey = import.meta.env.VITE_SILICONFLOW_KEY
    if (!apiKey || apiKey === 'sk-xxxxxx') {
      console.warn('[PageAgent] VITE_SILICONFLOW_KEY 未配置，跳过初始化')
      return
    }
    initAgent({
      baseURL: 'https://api.siliconflow.cn/v1',
      apiKey,
    })
  }

  const destroyAgent = () => {
    if (agentInstance.value) {
      try {
        agentInstance.value.panel.dispose()
      }
      catch (e) {
        console.error('Failed to dispose PageAgent panel:', e)
      }
      agentInstance.value = null
      agentReady.value = false
      lastTaskResult = { status: 'idle' }
      removeBridge()
    }
  }

  const executeAgent = async (command: string) => {
    const agent = agentInstance.value
    if (!agent) {
      console.warn('PageAgent not initialized')
      return null
    }
    await runTask(agent, command)
    return null
  }

  return {
    agentInstance,
    agentReady,
    initAgent,
    initFromDefaultModel,
    initFromEnv,
    destroyAgent,
    executeAgent,
  }
}
