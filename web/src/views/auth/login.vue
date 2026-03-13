<script lang="tsx" setup>
import * as GlobalAPI from '@/api'
import IconifyIcon from '@/components/IconifyIcon/index.vue'
import { usePageAgent } from '@/hooks/usePageAgent'

/* ---------- 登录业务 ---------- */
const form = ref({ username: 'admin', password: '123456' })
const formRef = ref()
const message = useMessage()
const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)

/* ---------- Page Agent ---------- */
const { initFromDefaultModel, destroyAgent } = usePageAgent()

/* ---------- 生命周期 ---------- */
onMounted(async () => {
  if (userStore.isLoggedIn) {
    router.push('/')
    return
  }

  await initFromDefaultModel()
})

onBeforeUnmount(() => {
  destroyAgent()
})

/* ---------- 登录操作 ---------- */
const handleLogin = async () => {
  if (!form.value.username || !form.value.password) {
    message.warning('请输入用户名和密码')
    return
  }

  loading.value = true
  try {
    const res = await GlobalAPI.login(form.value.username, form.value.password)
    // Check if response is ok
    if (res && res.ok) {
      const data = await res.json()
      if (data.code === 200) {
        message.success('登录成功')
        userStore.login({ token: data.data.token })
        // Use replace to avoid history stack issues
        router.replace('/')
      } else {
        message.error(data.msg || '登录失败')
      }
    } else {
      message.error('服务器响应错误')
    }
  } catch (error) {
    message.error('网络请求异常')
    console.error(error)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <!-- 动态背景装饰 -->
    <div class="background-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
    </div>

    <div class="login-wrapper">
      <div class="header">
        <div class="logo-area">
          <div class="logo-icon-wrapper">
            <IconifyIcon icon="hugeicons:ai-chat-02" :class="['text-42', 'text-white']" />
          </div>
        </div>
        <h1 class="app-name">
          大模型数据助手
        </h1>
      </div>

      <n-card
        :bordered="false"
        class="login-card"
      >
        <n-form
          ref="formRef"
          size="large"
          @submit.prevent="handleLogin"
        >
          <n-form-item
            path="username"
            :show-label="false"
          >
            <n-input
              v-model:value="form.username"
              placeholder="请输入用户名"
              class="custom-input"
            >
              <template #prefix>
                <div class="i-hugeicons:user text-[#999] transition-colors group-hover:text-[#7E6BF2]"></div>
              </template>
            </n-input>
          </n-form-item>
          <n-form-item
            path="password"
            :show-label="false"
          >
            <n-input
              v-model:value="form.password"
              type="password"
              placeholder="请输入密码"
              class="custom-input"
              show-password-on="click"
            >
              <template #prefix>
                <div class="i-hugeicons:lock-key text-[#999] transition-colors group-hover:text-[#7E6BF2]"></div>
              </template>
            </n-input>
          </n-form-item>
          <n-form-item>
            <n-button
              type="primary"
              block
              class="custom-button"
              :loading="loading"
              @click="handleLogin"
            >
              <span class="btn-text">立即登录</span>
              <template #icon>
                <div class="i-hugeicons:arrow-right-01"></div>
              </template>
            </n-button>
          </n-form-item>
        </n-form>
      </n-card>

      <div class="footer-decoration">
        <div class="feature-tags">
          <span class="tag"><i class="i-hugeicons:database-01"></i> 数据分析</span>
          <span class="dot">•</span>
          <span class="tag"><i class="i-hugeicons:ai-cloud-01"></i> 智能问答</span>
          <span class="dot">•</span>
          <span class="tag"><i class="i-hugeicons:chart-histogram"></i> 可视化</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f8f9fc;
  font-family: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}

/* 背景动态图形 */
.background-shapes {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 1;
}

.shape {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.6;
  animation: float 20s infinite ease-in-out;
}

.shape-1 {
  width: 500px;
  height: 500px;
  background: rgba(126, 107, 242, 0.15);
  top: -100px;
  left: -100px;
  animation-delay: 0s;
}

.shape-2 {
  width: 400px;
  height: 400px;
  background: rgba(99, 211, 255, 0.15);
  bottom: -50px;
  right: -50px;
  animation-delay: -5s;
}

.shape-3 {
  width: 300px;
  height: 300px;
  background: rgba(255, 159, 243, 0.1);
  top: 40%;
  left: 60%;
  animation-delay: -10s;
}

@keyframes float {
  0% { transform: translate(0, 0) rotate(0deg); }
  33% { transform: translate(30px, 50px) rotate(10deg); }
  66% { transform: translate(-20px, 20px) rotate(-5deg); }
  100% { transform: translate(0, 0) rotate(0deg); }
}

.login-wrapper {
  position: relative;
  z-index: 10;
  width: 420px;
  padding: 48px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 28px;
  box-shadow: 
    0 20px 40px -12px rgba(126, 107, 242, 0.1),
    0 0 0 1px rgba(255, 255, 255, 0.5) inset;
  animation: slideUp 0.8s cubic-bezier(0.2, 0.8, 0.2, 1);
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(40px); }
  to { opacity: 1; transform: translateY(0); }
}

.header {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 8px;
}

.logo-area {
  margin-bottom: 24px;
  animation: popIn 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) 0.2s backwards;
}

.logo-icon-wrapper {
  width: 72px;
  height: 72px;
  background: linear-gradient(135deg, #7E6BF2 0%, #9B8DFF 100%);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 12px 24px -8px rgba(126, 107, 242, 0.4);
  transform: rotate(-5deg);
  transition: transform 0.3s ease;
}

.logo-area:hover .logo-icon-wrapper {
  transform: rotate(0deg) scale(1.05);
}

@keyframes popIn {
  from { opacity: 0; transform: scale(0.5); }
  to { opacity: 1; transform: scale(1); }
}

.app-name {
  font-size: 26px;
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, #1a1a1a 0%, #4a4a4a 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 0.5px;
  animation: fadeIn 0.6s ease 0.3s backwards;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.login-card {
  background: transparent !important;
  border: none !important;
  animation: fadeIn 0.6s ease 0.5s backwards;
}

/* 输入框样式定制 */
:deep(.custom-input) {
  --n-border: 1px solid #eef0f5 !important;
  --n-border-hover: 1px solid #7E6BF2 !important;
  --n-border-focus: 1px solid #7E6BF2 !important;
  --n-box-shadow-focus: 0 0 0 3px rgba(126, 107, 242, 0.15) !important;
  border-radius: 16px !important;
  background-color: #f8f9fc !important;
  transition: all 0.3s ease;
}

:deep(.custom-input:hover),
:deep(.custom-input.n-input--focus) {
  background-color: #fff !important;
  transform: translateY(-1px);
}

:deep(.n-input__input-el) {
  height: 48px !important;
  color: #1a1a1a !important;
  font-weight: 500;
  font-size: 15px;
}

:deep(.n-input__prefix) {
  margin-right: 12px;
}

/* 按钮样式 */
.custom-button {
  height: 52px;
  background: linear-gradient(135deg, #7E6BF2 0%, #6b5ae0 100%);
  border: none;
  color: #fff;
  font-weight: 600;
  font-size: 16px;
  border-radius: 16px;
  transition: all 0.3s ease;
  margin-top: 16px;
  box-shadow: 0 8px 20px -6px rgba(126, 107, 242, 0.4);
}

.custom-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 24px -8px rgba(126, 107, 242, 0.5);
  background: linear-gradient(135deg, #8A79F5 0%, #7665EB 100%);
}

.custom-button:active {
  transform: translateY(0);
}

/* 底部装饰 */
.footer-decoration {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 8px;
  animation: fadeIn 0.6s ease 0.6s backwards;
}

.feature-tags {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #888;
  font-weight: 500;
  transition: color 0.2s;
}

.tag:hover {
  color: #7E6BF2;
}

.tag i {
  font-size: 14px;
}

.dot {
  color: #ddd;
  font-size: 12px;
}
</style>
