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

function findPanelInput(): HTMLInputElement | null {
  const panelEl = document.getElementById('page-agent-runtime_agent-panel')
  return panelEl?.querySelector('input[type="text"]') as HTMLInputElement | null
}

function submitViaPanel(command: string): Promise<void> {
  return new Promise((resolve) => {
    const agent = agentInstance.value
    // #region agent log
    console.log('[DBG-89b6b7] submitViaPanel called', { command, hasAgent: !!agent })
    fetch('http://127.0.0.1:7365/ingest/dad1413d-e35f-4bf5-a68f-d62b119da115',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'89b6b7'},body:JSON.stringify({sessionId:'89b6b7',location:'usePageAgent.ts:submitViaPanel',message:'submitViaPanel called',data:{command,hasAgent:!!agent},timestamp:Date.now(),hypothesisId:'A'})}).catch(()=>{});
    // #endregion
    if (!agent) { resolve(); return }

    const panel = agent.panel
    panel.show()
    panel.expand()

    const panelEl = document.getElementById('page-agent-runtime_agent-panel')
    const taskInput = findPanelInput()
    const allInputs = panelEl ? Array.from(panelEl.querySelectorAll('input')).map(el => ({ type: el.getAttribute('type'), cls: el.className })) : []
    // #region agent log
    console.log('[DBG-89b6b7] DOM lookup', { panelElExists: !!panelEl, taskInputExists: !!taskInput, taskInputTag: taskInput?.tagName, allInputs })
    fetch('http://127.0.0.1:7365/ingest/dad1413d-e35f-4bf5-a68f-d62b119da115',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'89b6b7'},body:JSON.stringify({sessionId:'89b6b7',location:'usePageAgent.ts:submitViaPanel:dom',message:'DOM lookup',data:{panelElExists:!!panelEl,taskInputExists:!!taskInput,taskInputTag:taskInput?.tagName,allInputs},timestamp:Date.now(),hypothesisId:'B'})}).catch(()=>{});
    // #endregion
    if (!taskInput) {
      agent.execute(command)
      resolve()
      return
    }

    const inputWrapper = taskInput.closest('[class*="inputSection"]')
    // #region agent log
    console.log('[DBG-89b6b7] inputWrapper', { found: !!inputWrapper, classes: inputWrapper ? Array.from(inputWrapper.classList) : null })
    fetch('http://127.0.0.1:7365/ingest/dad1413d-e35f-4bf5-a68f-d62b119da115',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'89b6b7'},body:JSON.stringify({sessionId:'89b6b7',location:'usePageAgent.ts:submitViaPanel:wrapper',message:'inputWrapper lookup',data:{wrapperFound:!!inputWrapper,wrapperClasses:inputWrapper?Array.from(inputWrapper.classList):null},timestamp:Date.now(),hypothesisId:'C'})}).catch(()=>{});
    // #endregion
    if (inputWrapper) {
      Array.from(inputWrapper.classList).forEach((cls) => {
        if (cls.includes('hidden')) inputWrapper.classList.remove(cls)
      })
    }

    taskInput.value = command
    taskInput.focus()
    // #region agent log
    console.log('[DBG-89b6b7] value set', { value: taskInput.value, len: taskInput.value.length })
    // #endregion

    setTimeout(() => {
      // #region agent log
      console.log('[DBG-89b6b7] dispatching Enter', { currentValue: taskInput.value, isConnected: taskInput.isConnected })
      // #endregion
      taskInput.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true, cancelable: true }),
      )
      resolve()
    }, 400)
  })
}

function exposeBridge() {
  // #region agent log
  console.log('[DBG-89b6b7] exposeBridge called, setting window.__aixPageAgent')
  // #endregion
  window.__aixPageAgent = {
    execute: async (command: string) => {
      // #region agent log
      console.log('[DBG-89b6b7] bridge.execute called', { command, hasAgent: !!agentInstance.value, agentReady: agentReady.value })
      // #endregion
      if (!agentInstance.value) {
        return { success: false, data: 'PageAgent not initialized' }
      }
      await submitViaPanel(command)
      return { success: true, data: 'Task submitted via panel' }
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
    // #region agent log
    console.log('[DBG-89b6b7] initAgent complete, agentReady:', agentReady.value, 'bridge exists:', !!window.__aixPageAgent)
    // #endregion
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
      removeBridge()
    }
  }

  const executeAgent = async (command: string) => {
    if (!agentInstance.value) {
      console.warn('PageAgent not initialized')
      return null
    }
    await submitViaPanel(command)
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
