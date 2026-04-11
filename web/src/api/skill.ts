/**
 * 技能相关 API 封装
 */
import { useUserStore } from '@/store/business/userStore'

export interface SkillInfo {
  name: string
  description: string
  enabled: boolean
  scope: 'common' | 'deep'
  path?: string
}

export interface SkillContent {
  name: string
  content: string
}

/**
 * 获取技能列表
 * @param scope 可选，'common' | 'deep'，不传则默认 common
 */
export async function fetch_skill_list(scope?: string): Promise<Response> {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/system/skill/list`)
  if (scope) {
    url.searchParams.append('scope', scope)
  }
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  return fetch(req)
}

/**
 * 获取技能详情内容（SKILL.md）
 * @param name 技能名称
 * @param scope 可选，'common' | 'deep'，不传则默认 common
 */
export async function fetch_skill_content(name: string, scope?: string): Promise<Response> {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/system/skill/content`)
  url.searchParams.append('name', name)
  if (scope) {
    url.searchParams.append('scope', scope)
  }
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  return fetch(req)
}

/**
 * 获取技能使用教程（AI 生成）
 * @param name 技能名称
 * @param scope 可选，'common' | 'deep'，不传则默认 common
 */
export async function fetch_skill_tutorial(name: string, scope?: string): Promise<Response> {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/system/skill/tutorial`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name, scope }),
  })
  return fetch(req)
}

/**
 * 从 GitHub URL 或 owner/repo 格式中提取 repo 标识
 */
function extractRepo(input: string): string {
  input = input.trim()
  // 已经是 owner/repo 格式
  if (/^[^\/]+\/[^\/]+$/.test(input)) {
    return input
  }
  // 完整 GitHub URL
  const match = input.match(/github\.com\/([^\/]+\/[^\/\?#]+)/)
  if (match) {
    return match[1]
  }
  return input
}

/**
 * 预览 GitHub 仓库中的技能（不安装）
 */
export async function preview_github_skills(repo: string): Promise<Response> {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/system/skill/preview`)
  url.searchParams.append('repo', extractRepo(repo))
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  return fetch(req)
}

/**
 * 从 GitHub 安装技能
 */
export async function install_from_github(repo: string, skills?: string[], scope?: string): Promise<Response> {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/system/skill/install/github`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ repo: extractRepo(repo), skills, scope }),
  })
  return fetch(req)
}

/**
 * 从 zip 包安装技能
 */
export async function install_from_zip(file: File, scope?: string): Promise<Response> {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const formData = new FormData()
  formData.append('file', file)
  formData.append('scope', scope ?? 'common')
  const url = new URL(`${location.origin}/sanic/system/skill/install/upload`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  })
  return fetch(req)
}

/**
 * 卸载技能
 */
export async function uninstall_skill(name: string, scope?: string): Promise<Response> {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/system/skill/uninstall`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name, scope }),
  })
  return fetch(req)
}

/**
 * 启用/禁用技能
 */
export async function toggle_skill(name: string, enabled: boolean, scope?: string): Promise<Response> {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/system/skill/toggle`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name, enabled, scope }),
  })
  return fetch(req)
}
