### 大模型数据助手

💡 **项目简介**

一个轻量级全链路可基于二次开发的大模型应用开发项目 🚀

基于 Dify 、Ollama 、Sanic 和 NL2SQL 📊 等技术构建的一站式大模型应用开发项目，采用 Vue3、TypeScript 和 Vite 5 打造现代UI。它支持通过 ECharts 📈 实现基于大模型的数据图形化问答，具备处理 CSV 文件 📂 表格数据查询的能力。同时，集成了第三方 RAG 系统 和 公网检索 🌐，以支持广泛的通用问答。

作为轻量级的大模型应用开发项目，Sanic-Web 🛠️ 支持快速迭代与扩展，助力大模型项目快速落地。🚀

🌈 **Live Demo**  
在线体验即将上线，敬请期待！

🎉 **特性**
- **核心技术栈**：Dify + Ollama + Sanic + NL2SQL
- **UI 框架**：Vue 3 + TypeScript + Vite 5
- **数据问答**：集成 ECharts大模型实现NL2SQL轻量级的数据图形化问答展示
- **表格问答**：支持 CSV格式文件的上传与基于大模型总结预处理和NL2SQL的表格数据问答
- **通用问答**：支持通用数据形式问答基于对接三方RAG系统+公网检索模式
- **应用架构**：作为一个轻量级全链路一站式大模型应用开发框架方便扩展落地
- **灵活部署**：支持 Docker 容器化部署，便于在各种环境中快速启动

🔧 **前置条件**
- Python 3.8+
- Poetry 1.8.3+
- Node.js 18.12.x+
- Pnpm 9.x
- Dify 0.7.1+

🔧 **大模型**
- Ollama
- qwen2/qwen2.5


🚀 **快速开始**
1. **安装依赖**  
   使用 pnpm 安装前端和后端依赖：
   ```bash
   pnpm install
   cd backend
   pip install -r requirements.txt