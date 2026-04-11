import { PageAgent } from 'page-agent'
import { ref, shallowRef } from 'vue'
import { fetch_model_list } from '@/api/aimodel'
import { getPageAgentConfigState } from '@/config'
import { pageAgentInstructions } from './pageAgentInstructions'

const BRIDGE_VERSION = '2.1.0'
let pageAgentConfigLogged = false

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

let PAGE_AGENT_MODEL = ''

const agentInstance = shallowRef<PageAgent | null>(null)
const agentReady = ref(false)
let lastTaskResult: TaskResult = { status: 'idle' }

function isPageAgentEnabled() {
  const config = getPageAgentConfigState()

  if (!pageAgentConfigLogged) {
    const rawValue = config.rawValue ?? '(default:true)'
    console.info(
      `[PageAgent] config resolved from ${config.source}, raw=${rawValue}, enabled=${config.enabled}`,
    )
    pageAgentConfigLogged = true
  }

  return config.enabled
}

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
// 面板定位：一次性设置面板位置（居中于可见的 input-card）
// ============================================

function positionPanel(wrapper: HTMLElement) {
  wrapper.style.transition = 'none'
  wrapper.style.transform = 'translateX(-50%)'

  // 登录页：居中于 form 表单下方
  const loginCard = document.querySelector('.login-container .login-card') as HTMLElement | null
  if (loginCard && loginCard.offsetParent !== null) {
    const formEl = loginCard.querySelector('form') as HTMLElement | null
    const ref = formEl || loginCard
    const r = ref.getBoundingClientRect()
    wrapper.style.left = `${r.left + r.width / 2}px`
    wrapper.style.top = `${r.bottom + 100}px`
    wrapper.style.bottom = '100px'
    wrapper.style.maxWidth = `${r.width*10}px`
    return
  }

  // 默认首页 / 聊天页的 .input-card
  const cards = document.querySelectorAll<HTMLElement>('.input-card')
  let foundCard: HTMLElement | null = null
  cards.forEach((c) => { if (c.offsetParent !== null) foundCard = c })

  if (!foundCard) {
    const contentEl = document.querySelector('.n-layout-scroll-container') as HTMLElement
      ?? document.querySelector('.n-layout-content') as HTMLElement
    if (!contentEl) return
    const r = contentEl.getBoundingClientRect()
    wrapper.style.left = `${r.left + r.width / 2}px`
    wrapper.style.bottom = '100px'
    return
  }

  const card: HTMLElement = foundCard
  const r = card.getBoundingClientRect()
  const isDefaultPage = !!card.closest('.default-page-container')
  const bottomOffset = isDefaultPage
    ? window.innerHeight - r.bottom - 240
    : window.innerHeight - r.top - 100

  wrapper.style.left = `${r.left + r.width / 2}px`
  wrapper.style.bottom = `${Math.max(bottomOffset, 8)}px`
  wrapper.style.maxWidth = `${r.width / 2}px`
}

// ============================================
// 保存最近一次初始化配置，用于 recreateAgent
// ============================================
let savedConfig: { baseURL: string, apiKey: string } | null = null

// ============================================
// 对外暴露的 composable
// ============================================
export function usePageAgent() {
  const initAgent = (config: { baseURL: string, apiKey: string }) => {
    if (!isPageAgentEnabled()) {
      console.info('[PageAgent] 已禁用，跳过初始化')
      destroyAgent()
      return null
    }

    if (!PAGE_AGENT_MODEL) {
      console.warn('[PageAgent] 模型未设置，请先调用 initFromDefaultModel 获取模型')
      return null
    }

    if (agentInstance.value) {
      destroyAgent()
    }
    savedConfig = config

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
    const wrapper = (agent.panel as any).wrapper as HTMLElement | undefined
    if (wrapper) {
      // 等 DOM 就绪后一次性定位
      requestAnimationFrame(() => positionPanel(wrapper))
    }

    agentInstance.value = agent
    agentReady.value = true
    lastTaskResult = { status: 'idle' }
    exposeBridge()
    console.log(`[PageAgent v${BRIDGE_VERSION}] initialized, model: ${PAGE_AGENT_MODEL}`)
    return agent
  }

  /**
   * 销毁当前面板，然后用同样的配置重新创建。
   * 面板会直接出现在新页面的正确位置，无任何移动动画。
   * 传入 delay 可等待 DOM（如 Vue transition）稳定后再创建。
   */
  const recreateAgent = (delay = 350) => {
    if (!isPageAgentEnabled() || !savedConfig) return
    destroyAgent()
    setTimeout(() => {
      if (savedConfig) initAgent(savedConfig)
    }, delay)
  }

  const initFromDefaultModel = async () => {
    if (!isPageAgentEnabled()) {
      console.info('[PageAgent] 已禁用，跳过默认模型初始化')
      return
    }

    try {
      const res = await fetch_model_list(undefined, 1)
      const list = Array.isArray(res?.data) ? res.data : Array.isArray(res) ? res : []
      const defaultModel = list.find((m: any) => m.default_model) || list[0]

      if (!defaultModel) {
        console.warn('[PageAgent] 无可用模型')
        return
      }

      if (!defaultModel.base_model) {
        console.warn('[PageAgent] 默认模型缺少 name 字段:', defaultModel)
        return
      }

      PAGE_AGENT_MODEL = defaultModel.base_model

      if (!defaultModel.api_domain) {
        console.warn('[PageAgent] 默认模型缺少 api_domain:', defaultModel.base_model)
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
    if (!isPageAgentEnabled()) {
      console.info('[PageAgent] 已禁用，跳过环境变量初始化')
      return
    }

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
    recreateAgent,
    executeAgent,
  }
}
