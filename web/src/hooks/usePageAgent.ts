import { PageAgent } from 'page-agent'
import { ref, shallowRef } from 'vue'
import { fetch_model_list } from '@/api/aimodel'
import { pageAgentInstructions } from './pageAgentInstructions'

declare global {
  interface Window {
    __aixPageAgent?: {
      execute: (command: string) => Promise<{ success: boolean, data: string }>
      isReady: () => boolean
      getStatus: () => string
    }
  }
}

const PAGE_AGENT_MODEL = 'qwen3.5-plus'

const agentInstance = shallowRef<PageAgent | null>(null)
const agentReady = ref(false)

function exposeBridge() {
  window.__aixPageAgent = {
    execute: async (command: string) => {
      if (!agentInstance.value) {
        return { success: false, data: 'PageAgent not initialized' }
      }
      return agentInstance.value.execute(command)
    },
    isReady: () => agentReady.value,
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
    })

    agent.panel.show()

    agentInstance.value = agent
    agentReady.value = true
    exposeBridge()
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

      console.log('[PageAgent] 初始化:', {
        model: PAGE_AGENT_MODEL,
        baseURL: defaultModel.api_domain,
        apiKey: defaultModel.api_key ? '***' : '(空)',
      })

      initAgent({
        baseURL: defaultModel.api_domain,
        apiKey: defaultModel.api_key || '',
      })
    }
    catch (e) {
      console.error('[PageAgent] 加载默认模型配置失败:', e)
    }
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
      removeBridge()
    }
  }

  const executeAgent = async (command: string) => {
    if (!agentInstance.value) {
      console.warn('PageAgent not initialized')
      return null
    }
    return agentInstance.value.execute(command)
  }

  return {
    agentInstance,
    agentReady,
    initAgent,
    initFromDefaultModel,
    destroyAgent,
    executeAgent,
  }
}
