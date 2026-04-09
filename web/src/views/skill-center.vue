<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useUserStore } from '@/store/business/userStore'
import {
  fetch_skill_list,
  fetch_skill_content,
  fetch_skill_tutorial,
  install_from_github,
  install_from_zip,
  preview_github_skills,
  uninstall_skill,
  type SkillInfo,
} from '@/api/skill'
import MarkdownPreview from '@/components/MarkdownPreview/index.vue'
import MarkdownInstance from '@/components/MarkdownPreview/plugins/markdown'
import 'highlight.js/styles/atom-one-dark-reasonable.css'

defineOptions({ name: 'SkillCenter' })

const router = useRouter()
const message = useMessage()
const dialog = useDialog()

// Tab
const activeScope = ref<'common' | 'deep'>('common')

// 已安装技能列表
const installedSkills = ref<SkillInfo[]>([])
const loadingInstalled = ref(false)

// 已安装技能搜索
const installedSearch = ref('')
const selectedForBatch = ref<string[]>([])

const filteredInstalled = computed(() => {
  const kw = installedSearch.value.trim().toLowerCase()
  if (!kw) return installedSkills.value
  return installedSkills.value.filter(
    (s) =>
      s.name.toLowerCase().includes(kw) ||
      (s.description && s.description.toLowerCase().includes(kw)),
  )
})

// GitHub 安装
const githubRepo = ref('')
const previewList = ref<SkillInfo[]>([])
const selectedForInstall = ref<string[]>([])
const loadingPreview = ref(false)
const installing = ref(false)

// Zip 上传
const showUploadModal = ref(false)
const uploadLoading = ref(false)

// 技能详情抽屉
const showSkillDrawer = ref(false)
const currentSkillContent = ref('')
const currentSkillName = ref('')
const currentSkillDesc = ref('')
const loadingSkillContent = ref(false)

// 使用教程抽屉
const showTutorialDrawer = ref(false)
const tutorialContent = ref('')
const tutorialRawContent = ref('')
const currentTutorialSkillName = ref('')
const loadingTutorial = ref(false)
const tutorialReader = ref<ReadableStreamDefaultReader | null>(null)

// 全选预览
const allPreviewSelected = computed({
  get: () => previewList.value.length > 0 && selectedForInstall.value.length === previewList.value.length,
  set: (val: boolean) => {
    selectedForInstall.value = val ? previewList.value.map((s) => s.name) : []
  },
})

// 全选已安装
const allInstalledSelected = computed({
  get: () => filteredInstalled.value.length > 0 && selectedForBatch.value.length === filteredInstalled.value.length,
  set: (val: boolean) => {
    selectedForBatch.value = val ? filteredInstalled.value.map((s) => s.name) : []
  },
})

async function loadInstalledSkills() {
  loadingInstalled.value = true
  try {
    const res = await fetch_skill_list(activeScope.value)
    const data = await res.json().catch(() => ({}))
    if (data?.code === 200 && Array.isArray(data?.data)) {
      installedSkills.value = data.data
    } else {
      installedSkills.value = []
    }
  } catch {
    installedSkills.value = []
  } finally {
    loadingInstalled.value = false
  }
}

async function handlePreview() {
  const repo = githubRepo.value.trim()
  if (!repo) {
    message.warning('请输入 GitHub 仓库，如 openclaw/openclaw')
    return
  }
  loadingPreview.value = true
  previewList.value = []
  selectedForInstall.value = []
  try {
    const res = await preview_github_skills(repo)
    const data = await res.json().catch(() => ({}))
    if (res.ok && data?.code === 200 && Array.isArray(data?.data)) {
      previewList.value = data.data
      if (previewList.value.length === 0) {
        message.info('该仓库未找到技能')
      }
    } else {
      message.error(data?.msg || data?.message || '预览失败')
    }
  } catch (e) {
    message.error('预览失败')
  } finally {
    loadingPreview.value = false
  }
}

async function handleInstallSelected() {
  if (selectedForInstall.value.length === 0) {
    message.warning('请先选择要安装的技能')
    return
  }
  installing.value = true
  try {
    const res = await install_from_github(githubRepo.value.trim(), selectedForInstall.value, activeScope.value)
    const data = await res.json().catch(() => ({}))
    if (res.ok && data?.code === 200) {
      message.success('安装成功')
      previewList.value = []
      selectedForInstall.value = []
      githubRepo.value = ''
      await loadInstalledSkills()
    } else {
      message.error(data?.msg || data?.message || '安装失败')
    }
  } catch (e) {
    message.error('安装失败')
  } finally {
    installing.value = false
  }
}

async function handleUninstall(skill: SkillInfo) {
  dialog.warning({
    title: '确认卸载',
    content: `确定要卸载技能「${skill.name}」吗？`,
    positiveText: '卸载',
    negativeText: '取消',
    async onPositiveClick() {
      const res = await uninstall_skill(skill.name, activeScope.value)
      const data = await res.json().catch(() => ({}))
      if (res.ok && data?.code === 200) {
        message.success('已卸载')
        await loadInstalledSkills()
      } else {
        message.error(data?.msg || data?.message || '卸载失败')
      }
    },
  })
}

async function handleBatchUninstall() {
  const names = selectedForBatch.value
  if (names.length === 0) {
    message.warning('请先选择技能')
    return
  }
  dialog.warning({
    title: '确认批量卸载',
    content: `确定要卸载选中的 ${names.length} 个技能吗？`,
    positiveText: '卸载',
    negativeText: '取消',
    async onPositiveClick() {
      for (const name of names) {
        await uninstall_skill(name, activeScope.value)
      }
      message.success(`已卸载 ${names.length} 个技能`)
      selectedForBatch.value = []
      await loadInstalledSkills()
    },
  })
}

async function handleZipUpload(file: File) {
  uploadLoading.value = true
  showUploadModal.value = false
  try {
    const res = await install_from_zip(file, activeScope.value)
    const data = await res.json().catch(() => ({}))
    if (res.ok && data?.code === 200) {
      message.success('安装成功')
      await loadInstalledSkills()
    } else {
      message.error(data?.msg || data?.message || '安装失败')
    }
  } catch (e) {
    message.error('安装失败')
  } finally {
    uploadLoading.value = false
  }
}

async function handleViewSkill(skill: SkillInfo) {
  currentSkillName.value = skill.name
  currentSkillDesc.value = ''
  currentSkillContent.value = ''
  showSkillDrawer.value = true
  loadingSkillContent.value = true
  try {
    const res = await fetch_skill_content(skill.name, activeScope.value)
    const data = await res.json().catch(() => ({}))
    if (res.ok && data?.code === 200 && data?.data?.content) {
      currentSkillName.value = data.data.name || skill.name
      currentSkillDesc.value = data.data.description || ''
      currentSkillContent.value = data.data.content
    } else {
      message.error(data?.msg || data?.message || '获取技能详情失败')
    }
  } catch (e) {
    message.error('获取技能详情失败')
  } finally {
    loadingSkillContent.value = false
  }
}

const renderedSkillContent = computed(() => {
  return MarkdownInstance.render(currentSkillContent.value || '')
})

const renderedDesc = computed(() => {
  return MarkdownInstance.render(currentSkillDesc.value || '')
})

async function handleViewTutorial(skill: SkillInfo) {
  currentTutorialSkillName.value = skill.name
  tutorialContent.value = ''
  showTutorialDrawer.value = true
  loadingTutorial.value = true
  tutorialReader.value = null

  const userStore = useUserStore()
  const token = userStore.getUserToken()

  try {
    const res = await fetch(`${location.origin}/sanic/system/skill/tutorial`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ name: skill.name, scope: activeScope.value }),
    })

    if (!res.ok) {
      throw new Error('请求失败')
    }

    // 创建一个转换流，将 SSE 格式转换为 MarkdownPreview 能处理的格式
    const decoder = new TextDecoder()
    let buffer = ''

    const transformStream = new TransformStream({
      transform(chunk, controller) {
        buffer += decoder.decode(chunk, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.content) {
                // 转换为纯 JSON 格式（供 standard model 使用）
                const formatted = JSON.stringify({ messageType: 'continue', content: data.content })
                controller.enqueue(new TextEncoder().encode(formatted + '\n'))
              } else if (data.done) {
                const formatted = JSON.stringify({ done: true })
                controller.enqueue(new TextEncoder().encode(formatted + '\n'))
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      },
      flush(controller) {
        if (buffer) {
          try {
            const data = JSON.parse(buffer.slice(5))
            if (data.content) {
              const formatted = JSON.stringify({ messageType: 'continue', content: data.content })
              controller.enqueue(new TextEncoder().encode(formatted + '\n'))
            } else if (data.done) {
              const formatted = JSON.stringify({ done: true })
              controller.enqueue(new TextEncoder().encode(formatted + '\n'))
            }
          } catch {
            // ignore
          }
        }
      }
    })

    const reader = res.body?.pipeThrough(transformStream).getReader()
    tutorialReader.value = reader
    loadingTutorial.value = false
  } catch (e) {
    message.error('获取使用教程失败')
    loadingTutorial.value = false
  }
}

function handleBack() {
  router.push({ name: 'ChatIndex' })
}

function onScopeChange(scope: 'common' | 'deep') {
  activeScope.value = scope
  selectedForBatch.value = []
  installedSearch.value = ''
  loadInstalledSkills()
}

onMounted(() => {
  loadInstalledSkills()
})
</script>

<template>
  <div class="skill-center-page">
    <div class="skill-center-header">
      <div
        class="skill-center-back"
        @click="handleBack"
      >
        <div class="i-hugeicons:arrow-left-01 text-20"></div>
        <span>返回</span>
      </div>
      <h1 class="skill-center-title">
        <div class="skill-center-title-icon i-hugeicons:magic-wand-01 text-22 mr-2"></div>
        技能中心
      </h1>
    </div>

    <!-- Tab 切换 -->
    <div class="skill-center-tabs">
      <n-tabs v-model:value="activeScope" type="segment" @update:value="onScopeChange">
        <n-tab name="common">智能问答</n-tab>
        <n-tab name="deep">深度问数</n-tab>
      </n-tabs>
    </div>

    <!-- 智能问答/深度问数 Tab 统一内容 -->
    <div class="skill-center-body">
      <!-- 安装区域 -->
      <div class="install-section">
        <div class="install-title text-14 font-medium mb-3">安装技能</div>

        <div class="flex gap-2 mb-3">
          <n-input
            v-model:value="githubRepo"
            :placeholder="activeScope === 'common' ? '输入 GitHub Skill仓库地址 - 安装到智能问答' : '输入 GitHub Skill仓库地址 - 安装到深度问数'"
            class="flex-1"
            @keydown.enter.prevent="handlePreview"
          />
          <n-button type="primary" :loading="loadingPreview" @click="handlePreview">
            搜索技能
          </n-button>
          <n-button @click="showUploadModal = true">
            上传 zip 包
          </n-button>
        </div>

        <!-- GitHub 预览列表 -->
        <div v-if="loadingPreview" class="py-4 text-center text-gray-400">
          <n-spin size="small" /> 搜索中...
        </div>
        <div v-else-if="previewList.length > 0" class="preview-section">
          <div class="flex justify-between items-center mb-2">
            <span class="text-12 text-gray-500">
              选择要安装的技能（共 {{ previewList.length }} 个）：
            </span>
            <n-checkbox
              v-model:checked="allPreviewSelected"
              label="全选"
            />
          </div>
          <n-checkbox-group v-model:value="selectedForInstall">
            <n-space>
              <n-checkbox
                v-for="s in previewList"
                :key="s.name"
                :value="s.name"
                :label="s.name"
              />
            </n-space>
          </n-checkbox-group>
          <n-button
            type="primary"
            :disabled="selectedForInstall.length === 0"
            :loading="installing"
            class="mt-3"
            @click="handleInstallSelected"
          >
            安装选中的技能 ({{ selectedForInstall.length }})
          </n-button>
        </div>
      </div>

      <!-- 已安装技能列表 -->
      <div class="installed-section mt-6">
        <div class="flex justify-between items-center mb-3">
          <div class="install-title text-14 font-medium">已安装技能</div>
          <div class="flex gap-2 items-center">
            <n-input
              v-model:value="installedSearch"
              placeholder="搜索..."
              size="small"
              clearable
              class="w-48"
            />
            <!-- 批量操作按钮（deep tab 不显示） -->
            <template v-if="activeScope === 'common'">
              <n-button
                v-if="selectedForBatch.length > 0"
                size="small"
                type="error"
                @click="handleBatchUninstall"
              >
                卸载 ({{ selectedForBatch.length }})
              </n-button>
            </template>
          </div>
        </div>

        <div v-if="loadingInstalled" class="py-8 text-center">
          <n-spin size="medium" />
        </div>
        <div v-else-if="filteredInstalled.length === 0" class="py-8 text-center text-gray-400">
          {{ installedSearch ? '未找到匹配技能' : '暂无已安装技能' }}
        </div>
        <div v-else class="skill-list">
          <!-- 全选行（仅 common tab 显示） -->
          <div v-if="activeScope === 'common'" class="flex items-center gap-2 mb-2 pl-2">
            <n-checkbox
              v-model:checked="allInstalledSelected"
              label="全选"
            />
          </div>
          <div
            v-for="skill in filteredInstalled"
            :key="skill.name"
            class="skill-card"
          >
            <!-- common tab: 带复选框的卡片 -->
            <template v-if="activeScope === 'common'">
              <div class="skill-card-left">
                <n-checkbox
                  :value="skill.name"
                  v-model:checked="selectedForBatch"
                />
                <div class="skill-card-info" @click="handleViewSkill(skill)">
                  <div class="skill-card-header">
                    <div class="skill-card-icon">
                      <div class="i-hugeicons:magic-wand-01 text-16"></div>
                    </div>
                    <span class="skill-card-name">{{ skill.name }}</span>
                  </div>
                  <div class="skill-card-desc">{{ skill.description || '暂无描述' }}</div>
                </div>
              </div>
              <div class="skill-card-actions">
                <n-button size="small" type="info" @click="handleViewTutorial(skill)">
                  使用教程
                </n-button>
                <n-button size="small" type="error" @click="handleUninstall(skill)">
                  卸载
                </n-button>
              </div>
            </template>
            <!-- deep tab: 不带复选框的卡片 -->
            <template v-else>
              <div class="skill-card-info" @click="handleViewSkill(skill)">
                <div class="skill-card-header">
                  <div class="skill-card-icon">
                    <div class="i-hugeicons:magic-wand-01 text-16"></div>
                  </div>
                  <span class="skill-card-name">{{ skill.name }}</span>
                </div>
                <div class="skill-card-desc">{{ skill.description || '暂无描述' }}</div>
              </div>
              <div class="skill-card-actions">
                <n-button size="small" type="info" @click="handleViewTutorial(skill)">
                  使用教程
                </n-button>
                <n-button size="small" type="error" @click="handleUninstall(skill)">
                  卸载
                </n-button>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- Zip 上传弹窗 -->
    <n-modal v-model:show="showUploadModal" preset="dialog" title="上传技能 zip 包">
      <n-upload
        accept=".zip"
        :max="1"
        @change="(options: any) => {
          const file = options?.file?.file
          if (file) handleZipUpload(file)
        }"
      >
        <n-button :loading="uploadLoading">选择 zip 文件</n-button>
      </n-upload>
    </n-modal>

    <!-- 技能详情抽屉 -->
    <n-drawer v-model:show="showSkillDrawer" :width="900" placement="right">
      <n-drawer-content closable>
        <template #header>
          <div class="skill-drawer-header">
            <div class="i-hugeicons:magic-wand-01 text-18 text-primary mr-2"></div>
            <span>{{ currentSkillName }}</span>
          </div>
        </template>
        <div class="skill-drawer-meta">
          <div class="skill-drawer-name">{{ currentSkillName }}</div>
        </div>
        <div v-if="currentSkillDesc" class="skill-drawer-desc" v-html="renderedDesc"></div>
        <n-divider class="mt-4" />
        <div v-if="loadingSkillContent" class="flex justify-center items-center py-10">
          <n-spin size="medium" />
        </div>
        <div
          v-else
          class="skill-drawer-content markdown-wrapper"
          v-html="renderedSkillContent"
        ></div>
      </n-drawer-content>
    </n-drawer>

    <!-- 使用教程抽屉 -->
    <n-drawer v-model:show="showTutorialDrawer" :width="900" placement="right">
      <n-drawer-content closable>
        <template #header>
          <div class="skill-drawer-header">
            <div class="i-hugeicons:book-open-01 text-18 text-primary mr-2"></div>
            <span>{{ currentTutorialSkillName }} 使用教程</span>
          </div>
        </template>
        <div v-if="loadingTutorial" class="flex justify-center items-center py-10">
          <n-spin size="medium" />
          <span class="ml-3 text-gray-500">AI 正在生成教程...</span>
        </div>
        <MarkdownPreview
          v-else
          :reader="tutorialReader"
          :is-init="true"
          :is-view="true"
          class="skill-drawer-content"
        />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style lang="scss" scoped>
@use "@/styles/typography.scss" as *;

$font-family-base: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
  'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
$text-primary: #1e293b;
$text-secondary: #64748b;
$text-muted: #94a3b8;
$border-color: #e2e8f0;
$radius-md: 12px;
$radius-lg: 16px;
$primary-color: #7e6bf2;

.skill-center-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  font-family: $font-family-base;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.6) 0%, rgba(255, 255, 255, 0) 24px);
}

.skill-center-header {
  flex-shrink: 0;
  padding: 20px 24px 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
}

.skill-center-back {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin: -8px 0 -8px -12px;
  border-radius: $radius-md;
  color: $text-secondary;
  font-size: 14px;
  cursor: pointer;
  transition: color 0.2s, background 0.2s;

  &:hover {
    color: $primary-color;
    background: rgba(126, 107, 242, 0.08);
  }
}

.skill-center-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: $text-primary;
  display: flex;
  align-items: center;
}

.skill-center-title-icon {
  color: $primary-color;
}

.skill-center-tabs {
  flex-shrink: 0;
  padding: 12px 24px 0;
}

.skill-center-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px 32px;
  -webkit-overflow-scrolling: touch;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: $border-color;
    border-radius: 3px;
  }
}

.install-section {
  padding: 16px;
  border-radius: $radius-lg;
  border: 1px solid rgba(226, 232, 240, 0.7);
  background: rgba(255, 255, 255, 0.5);
}

.installed-section {
  padding: 16px;
  border-radius: $radius-lg;
  border: 1px solid rgba(226, 232, 240, 0.7);
  background: rgba(255, 255, 255, 0.5);
}

.preview-section {
  padding: 12px;
  border-radius: $radius-md;
  background: rgba(126, 107, 242, 0.04);
  border: 1px solid rgba(126, 107, 242, 0.1);
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: $radius-md;
  border: 1px solid rgba(226, 232, 240, 0.7);
  background: rgba(255, 255, 255, 0.6);
  transition: border-color 0.2s, box-shadow 0.2s;

  &:hover {
    border-color: rgba(126, 107, 242, 0.3);
    box-shadow: 0 2px 8px rgba(126, 107, 242, 0.06);
  }
}

.skill-card-left {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.skill-card-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.skill-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.skill-card-icon {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: linear-gradient(135deg, rgba(126, 107, 242, 0.12) 0%, rgba(126, 107, 242, 0.06) 100%);
  color: $primary-color;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.skill-card-name {
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
}

.skill-card-desc {
  font-size: 12px;
  color: $text-secondary;
  line-height: 1.5;
  word-break: break-word;
  margin-left: 36px;
}

.skill-card-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.skill-drawer-header {
  display: flex;
  align-items: center;
  font-weight: 600;
}

.skill-drawer-header .text-primary {
  color: $primary-color;
}

.skill-drawer-meta {
  margin-bottom: 8px;
}

.skill-drawer-name {
  font-size: 22px;
  font-weight: 700;
  color: $text-primary;
  margin-bottom: 8px;
}

.skill-drawer-desc {
  font-size: 15px;
  color: $text-secondary;
  line-height: 1.7;

  p {
    margin: 0.5em 0;
  }
}

.skill-drawer-content {
  padding: 0;
  overflow-y: auto;

  background-color: #fff;
  color: $text-primary;
  font-family: "Plus Jakarta Sans", $font-family-base !important;
  font-size: 15px;
  line-height: 1.8;

  * {
    font-family: "Plus Jakarta Sans", $font-family-base !important;
  }

  h1 {
    font-size: 1.4em;
    font-weight: 700;
    color: $text-primary;
    margin: 1em 0 0.5em;
    padding-bottom: 0.4em;
    border-bottom: 1px solid $border-color;
  }

  h2 {
    font-size: 1.2em;
    font-weight: 600;
    color: $text-primary;
    margin: 1em 0 0.4em;
  }

  h3 {
    font-size: 1em;
    font-weight: 600;
    color: $text-primary;
    margin: 0.8em 0 0.3em;
  }

  p {
    margin: 0.6em 0;
  }

  ul, ol {
    margin: 0.5em 0;
    padding-left: 1.5em;
  }

  li {
    margin: 0.3em 0;
  }

  // 代码块
  pre {
    margin: 0.8em 0;
    border-radius: 6px;
    overflow: hidden;

    code {
      display: block;
      padding: 16px 20px;
      overflow-x: auto;
      font-size: 13.5px;
      line-height: 1.65;
    }
  }

  // 行内代码
  code {
    font-family: $font-family-mono !important;
    font-size: 0.9em;
  }

  :not(pre) > code {
    background: rgba(0, 0, 0, 0.06);
    padding: 2px 6px;
    border-radius: 3px;
    color: #c7254e;
  }

  table {
    width: 100%;
    margin: 0.8em 0;
    border-collapse: collapse;
    font-size: 14px;
  }

  th, td {
    padding: 8px 12px;
    border: 1px solid $border-color;
    text-align: left;
  }

  th {
    background: #f8f9fa;
    font-weight: 600;
  }

  blockquote {
    margin: 0.8em 0;
    padding: 8px 16px;
    border-left: 3px solid $primary-color;
    background: rgba(126, 107, 242, 0.04);
    color: $text-secondary;
  }

  hr {
    border: none;
    border-top: 1px solid $border-color;
    margin: 1.2em 0;
  }

  img {
    max-width: 100%;
    border-radius: 4px;
  }

  a {
    color: $primary-color;
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }
}
</style>
