const DISABLED_VALUES = new Set(['false', '0', 'off', 'no'])

type PageAgentConfigSource = 'runtime' | 'build' | 'default'

interface PageAgentConfigState {
  enabled: boolean
  rawValue?: string
  source: PageAgentConfigSource
}

function normalizeFlagValue(value: unknown) {
  if (typeof value !== 'string') return undefined

  const normalized = value.trim()
  return normalized || undefined
}

export function getPageAgentConfigState(): PageAgentConfigState {
  const runtimeValue = normalizeFlagValue(window.__AIX_RUNTIME_CONFIG__?.VITE_ENABLE_PAGE_AGENT)
  if (runtimeValue !== undefined) {
    return {
      enabled: !DISABLED_VALUES.has(runtimeValue.toLowerCase()),
      rawValue: runtimeValue,
      source: 'runtime',
    }
  }

  const buildValue = normalizeFlagValue(__AIX_PAGE_AGENT_BUILD_FLAG__)
  if (buildValue !== undefined) {
    return {
      enabled: !DISABLED_VALUES.has(buildValue.toLowerCase()),
      rawValue: buildValue,
      source: 'build',
    }
  }

  return {
    enabled: true,
    source: 'default',
  }
}
