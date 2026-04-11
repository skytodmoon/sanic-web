<script lang="ts" setup>
import type { SkillInfo } from '@/api/skill'

const props = defineProps<{
  visible: boolean
  skills: SkillInfo[]
  filterText: string
  highlightIndex: number
}>()

const emit = defineEmits<{
  (e: 'select', name: string): void
  (e: 'close'): void
}>()

const filteredSkills = computed(() => {
  if (!props.filterText) return props.skills
  const text = props.filterText.toLowerCase()
  return props.skills.filter(
    s => s.name.toLowerCase().includes(text) || s.description.toLowerCase().includes(text),
  )
})

function handleSelect(skill: SkillInfo) {
  emit('select', skill.name)
}
</script>

<template>
  <transition name="skill-popup-fade">
    <div
      v-if="visible && skills.length > 0"
      class="skill-command-popup"
    >
      <div class="popup-header">
        <span class="popup-title">选择技能</span>
        <span class="popup-hint">Tab 选择 · Esc 关闭</span>
      </div>
      <div class="popup-list">
        <template v-if="filteredSkills.length > 0">
          <div
            v-for="(skill, idx) in filteredSkills"
            :key="skill.name"
            class="popup-item"
            :class="{ active: idx === highlightIndex }"
            @mousedown.prevent="handleSelect(skill)"
          >
            <div class="item-icon">
              <div class="i-hugeicons:magic-wand-01 text-16"></div>
            </div>
            <div class="item-content">
              <span class="item-name">/{{ skill.name }}</span>
              <span class="item-desc">{{ skill.description }}</span>
            </div>
          </div>
        </template>
        <div
          v-else
          class="popup-empty"
        >
          <span>无匹配技能</span>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.skill-command-popup {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin-bottom: 6px;
  background: #fff;
  border: 1px solid #e8e8ed;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
  z-index: 1000;
  max-height: 320px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px 6px;
  border-bottom: 1px solid #f0f0f5;
}

.popup-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
}

.popup-hint {
  font-size: 11px;
  color: #aaa;
}

.popup-list {
  overflow-y: auto;
  padding: 4px;
  max-height: 270px;
}

.popup-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.popup-item:hover,
.popup-item.active {
  background: #f5f3ff;
}

.item-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #f0edff;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #7e6bf2;
}

.item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-name {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.item-desc {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.popup-empty {
  padding: 20px;
  text-align: center;
  color: #ccc;
  font-size: 13px;
}

/* Transition */
.skill-popup-fade-enter-active,
.skill-popup-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.skill-popup-fade-enter-from,
.skill-popup-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
