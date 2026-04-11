<script lang="ts" setup>
const props = defineProps<{
  question: string
  threadId: string
  loading?: boolean
  answered?: boolean
}>()

const emit = defineEmits<{
  (e: 'submit', data: { threadId: string, userInput: string }): void
}>()

const userInput = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)

function handleSubmit() {
  const text = userInput.value.trim()
  if (!text) return
  emit('submit', { threadId: props.threadId, userInput: text })
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
}

onMounted(() => {
  nextTick(() => inputRef.value?.focus())
})
</script>

<template>
  <div class="agent-input-request" :class="{ answered }">
    <div class="request-header">
      <div class="request-icon">
        <div class="i-hugeicons:message-question-01 text-18"></div>
      </div>
      <span class="request-label">智能体提问</span>
    </div>
    <div class="request-question">
      {{ question }}
    </div>
    <div v-if="!answered" class="request-input-area">
      <textarea
        ref="inputRef"
        v-model="userInput"
        class="request-input"
        placeholder="输入你的回答..."
        rows="2"
        :disabled="loading"
        @keydown="handleKeydown"
      />
      <button
        class="request-submit"
        :disabled="!userInput.trim() || loading"
        @click="handleSubmit"
      >
        <div v-if="loading" class="i-svg-spinners:dots-scale-middle text-14"></div>
        <template v-else>
          <div class="i-hugeicons:arrow-up-01 text-16"></div>
        </template>
      </button>
    </div>
  </div>
</template>

<style scoped>
.agent-input-request {
  margin: 12px 0;
  padding: 16px;
  background: linear-gradient(135deg, #faf8ff 0%, #f0edff 100%);
  border: 1px solid #e8e3ff;
  border-radius: 12px;
  transition: all 0.2s ease;
}

.agent-input-request.answered {
  opacity: 0.7;
  background: #f8f8fb;
  border-color: #eee;
}

.request-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.request-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: #7e6bf2;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

.request-label {
  font-size: 13px;
  font-weight: 600;
  color: #7e6bf2;
}

.request-question {
  font-size: 14px;
  color: #333;
  line-height: 1.6;
  margin-bottom: 12px;
  white-space: pre-wrap;
}

.request-input-area {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.request-input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd6fe;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  outline: none;
  background: #fff;
  color: #333;
  font-family: inherit;
  transition: border-color 0.2s;
}

.request-input:focus {
  border-color: #7e6bf2;
  box-shadow: 0 0 0 3px rgba(126, 107, 242, 0.1);
}

.request-input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.request-submit {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  background: #7e6bf2;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
}

.request-submit:hover:not(:disabled) {
  background: #6b5ad4;
  transform: translateY(-1px);
}

.request-submit:disabled {
  background: #c4bce8;
  cursor: not-allowed;
}
</style>
