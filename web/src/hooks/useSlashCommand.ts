import type { Ref } from 'vue'
import type { InputInst } from 'naive-ui'
import type { SkillInfo } from '@/api/skill'
import { fetch_skill_list } from '@/api/skill'

export function useSlashCommand(
  inputRef: Ref<InputInst | null | undefined>,
  inputText: Ref<string>,
  enabled: Ref<boolean> = ref(true),
) {
  const allSkills = ref<SkillInfo[]>([])
  const selectedSkills = ref<string[]>([])
  const showPopup = ref(false)
  const filterText = ref('')
  const highlightIndex = ref(0)
  const slashStartIndex = ref(-1)
  let skillsLoaded = false

  // 懒加载技能列表
  async function ensureSkillsLoaded() {
    if (skillsLoaded) return
    try {
      const res = await fetch_skill_list('common')
      const data = await res.json()
      if (data?.code === 200 && Array.isArray(data?.data)) {
        allSkills.value = data.data.filter((s: SkillInfo) => s.enabled)
      }
      skillsLoaded = true
    }
    catch (e) {
      console.error('Failed to load skills:', e)
    }
  }

  // 获取过滤后的技能列表
  const filteredSkills = computed(() => {
    if (!filterText.value) return allSkills.value
    const text = filterText.value.toLowerCase()
    return allSkills.value.filter(
      s => s.name.toLowerCase().includes(text) || s.description.toLowerCase().includes(text),
    )
  })

  // 获取 textarea DOM 元素
  function getTextarea(): HTMLTextAreaElement | null {
    const inputEl = inputRef.value as any
    return inputEl?.$el?.querySelector('textarea') ?? null
  }

  // 检测 / 命令
  function detectSlashCommand() {
    if (!enabled.value) return

    const textarea = getTextarea()
    if (!textarea) return

    const cursorPos = textarea.selectionStart
    const text = inputText.value

    // 向前查找最近的 /
    let slashPos = -1
    for (let i = cursorPos - 1; i >= 0; i--) {
      if (text[i] === '/') {
        // / 必须在行首或前面是空格
        if (i === 0 || text[i - 1] === ' ' || text[i - 1] === '\n') {
          slashPos = i
        }
        break
      }
      // 遇到空格或换行就停止查找
      if (text[i] === ' ' || text[i] === '\n') break
    }

    if (slashPos >= 0) {
      slashStartIndex.value = slashPos
      filterText.value = text.substring(slashPos + 1, cursorPos)
      highlightIndex.value = 0
      if (!showPopup.value) {
        ensureSkillsLoaded()
        showPopup.value = true
      }
    }
    else {
      closePopup()
    }
  }

  function closePopup() {
    showPopup.value = false
    filterText.value = ''
    highlightIndex.value = 0
    slashStartIndex.value = -1
  }

  // 选中技能
  function selectSkill(name: string) {
    if (!selectedSkills.value.includes(name)) {
      selectedSkills.value.push(name)
    }

    // 移除输入框中 /xxx 文本
    if (slashStartIndex.value >= 0) {
      const textarea = getTextarea()
      const cursorPos = textarea?.selectionStart ?? inputText.value.length
      const before = inputText.value.substring(0, slashStartIndex.value)
      const after = inputText.value.substring(cursorPos)
      inputText.value = before + after

      // 恢复光标位置
      nextTick(() => {
        if (textarea) {
          textarea.selectionStart = before.length
          textarea.selectionEnd = before.length
          textarea.focus()
        }
      })
    }

    closePopup()
  }

  // 移除已选技能
  function removeSkill(name: string) {
    const idx = selectedSkills.value.indexOf(name)
    if (idx >= 0) {
      selectedSkills.value.splice(idx, 1)
    }
  }

  // 处理键盘事件，返回 true 表示已消费事件
  function handleKeydown(e: KeyboardEvent): boolean {
    if (!enabled.value) return false
    if (!showPopup.value) return false

    const skills = filteredSkills.value
    if (skills.length === 0) {
      if (e.key === 'Escape') {
        closePopup()
        return true
      }
      return false
    }

    switch (e.key) {
      case 'ArrowUp':
        highlightIndex.value = highlightIndex.value <= 0
          ? skills.length - 1
          : highlightIndex.value - 1
        return true

      case 'ArrowDown':
        highlightIndex.value = highlightIndex.value >= skills.length - 1
          ? 0
          : highlightIndex.value + 1
        return true

      case 'Tab':
      case 'Enter':
        if (skills[highlightIndex.value]) {
          selectSkill(skills[highlightIndex.value].name)
        }
        return true

      case 'Escape':
        closePopup()
        return true
    }

    return false
  }

  // 清空选中（发送消息后调用）
  function clearSelectedSkills() {
    selectedSkills.value = []
  }

  // 监听输入变化
  watch(inputText, () => {
    // 使用 nextTick 确保光标位置已更新
    nextTick(() => detectSlashCommand())
  })

  // 当 enabled 变为 false 时，清空选中的技能和关闭弹窗
  watch(enabled, (newEnabled) => {
    if (!newEnabled) {
      selectedSkills.value = []
      closePopup()
    }
  })

  return {
    allSkills,
    selectedSkills,
    filteredSkills,
    showPopup,
    filterText,
    highlightIndex,
    handleKeydown,
    selectSkill,
    removeSkill,
    closePopup,
    clearSelectedSkills,
  }
}
