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
