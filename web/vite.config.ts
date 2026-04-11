import fs from 'fs'
import path from 'path'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import UnoCSS from 'unocss/vite'
import AutoImport from 'unplugin-auto-import/vite'

import IconsResolver from 'unplugin-icons/resolver'

import Icons from 'unplugin-icons/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import Components from 'unplugin-vue-components/vite'
import { defineConfig, loadEnv } from 'vite'

import raw from 'vite-raw-plugin'

function getPackageName(id: string) {
  const nodeModulesSegment = id.split('node_modules/').pop()
  if (!nodeModulesSegment) return null

  const normalized = nodeModulesSegment.replace(/\\/g, '/')
  const segments = normalized.split('/')

  if (segments[0]?.startsWith('@')) {
    return segments.slice(0, 2).join('/')
  }

  return segments[0] || null
}

function parseSimpleEnv(content: string) {
  const parsed: Record<string, string> = {}

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue

    const separatorIndex = line.indexOf('=')
    if (separatorIndex === -1) continue

    const key = line.slice(0, separatorIndex).trim()
    let value = line.slice(separatorIndex + 1).trim()

    if (
      (value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith('\'') && value.endsWith('\''))
    ) {
      value = value.slice(1, -1)
    }

    parsed[key] = value
  }

  return parsed
}

function readRootPageAgentBuildFlag(mode: string) {
  const rootModeMap: Record<string, string> = {
    development: 'dev',
    production: 'pro',
    test: 'test',
  }
  const rootMode = rootModeMap[mode] || mode
  const envFilePath = path.resolve(__dirname, '..', `.env.${rootMode}`)

  if (!fs.existsSync(envFilePath)) {
    return ''
  }

  const parsedEnv = parseSimpleEnv(fs.readFileSync(envFilePath, 'utf8'))
  return parsedEnv.VITE_ENABLE_PAGE_AGENT?.trim() || ''
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const pageAgentBuildFlag = readRootPageAgentBuildFlag(mode)

  return {
    base: env.VITE_ROUTER_MODE === 'hash' ? '' : '/',
    assetsInclude: ['**/*.png'],
    server: {
      port: 2048,
      cors: true,
      proxy: {
        '/spark': {
          target: 'https://spark-api-open.xf-yun.com',
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/spark/, ''),
        },
        '/siliconflow': {
          target: 'https://api.siliconflow.cn',
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/siliconflow/, ''),
        },
        '/sanic': {
          target: 'http://localhost:8088',
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/sanic/, ''),
          // SSE 流式响应需要较长超时（DeepAgent 报告生成耗时较长）
          timeout: 1200000, // 20分钟
          proxyTimeout: 1200000,
        },
        '/sse': {
          target: 'http://localhost:3300',
          ws: true,
          rewrite: (path) => path.replace(/^\/sse/, 'sse'),
        },
        '/messages': {
          target: 'http://localhost:3300',
          ws: true,
          rewrite: (path) => path.replace(/^\/messages/, 'messages'),
        },
      },
    },
    plugins: [
      UnoCSS(),
      vue(),
      raw({
        fileRegex: /\.md$/,
      }),
      vueJsx(),
      AutoImport({
        include: [/\.[tj]sx?$/, /\.vue\??/],
        imports: [
          'vue',
          'vue-router',
          '@vueuse/core',
          {
            'vue': ['createVNode', 'render'],
            'vue-router': [
              'createRouter',
              'createWebHistory',
              'useRouter',
              'useRoute',
            ],
            'uuid': [['v4', 'uuidv4']],
            'lodash-es': [['*', '_']],
            'naive-ui': [
              'useDialog',
              'useMessage',
              'useNotification',
              'useLoadingBar',
            ],
          },
          {
            from: 'vue',
            imports: [
              'App',
              'VNode',
              'ComponentInternalInstance',
              'GlobalComponents',
              'SetupContext',
              'PropType',
            ],
            type: true,
          },
          {
            from: 'vue-router',
            imports: ['RouteRecordRaw', 'RouteLocationRaw'],
            type: true,
          },
        ],
        resolvers: mode === 'development' ? [] : [NaiveUiResolver()],
        dirs: [
          './src/hooks',
          './src/store/business',
          './src/store/transform',
          './src/store/hooks/**',
        ],
        dts: './auto-imports.d.ts',
        eslintrc: {
          enabled: true,
        },
        vueTemplate: true,
      }),
      Components({
        directoryAsNamespace: true,
        collapseSamePrefixes: true,
        resolvers: [
          IconsResolver({
            prefix: 'auto-icon',
          }),
          NaiveUiResolver(),
        ],
      }),
      // Auto use Iconify icon
      Icons({
        autoInstall: true,
        compiler: 'vue3',
        scale: 1.2,
        defaultStyle: '',
        defaultClass: 'unplugin-icon',
        jsx: 'react',
      }),
    ],
    resolve: {
      extensions: [
        '.mjs',
        '.js',
        '.ts',
        '.jsx',
        '.tsx',
        '.json',
        '.less',
        '.css',
      ],
      alias: [
        {
          find: '@',
          replacement: path.resolve(__dirname, 'src'),
        },
      ],
    },
    define: {
      'process.env.NODE_ENV': JSON.stringify(mode),
      __AIX_PAGE_AGENT_BUILD_FLAG__: JSON.stringify(pageAgentBuildFlag),
    },
    build: {
      chunkSizeWarningLimit: 800,
      rollupOptions: {
        onwarn(warning, warn) {
          const warningId = typeof warning.id === 'string' ? warning.id : ''
          const warningMessage = typeof warning.message === 'string' ? warning.message : ''

          if (
            warningId.includes('/node_modules/.pnpm/zod@')
            && warningMessage.includes('contains an annotation that Rollup cannot interpret')
          ) {
            return
          }

          if (
            warningId.includes('@page-agent/page-controller')
            && warningMessage.includes('Use of eval')
          ) {
            return
          }

          warn(warning)
        },
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return

            const packageName = getPackageName(id)
            if (!packageName) return 'vendor'

            if (
              packageName === 'vue'
              || packageName === 'vue-router'
              || packageName === 'pinia'
              || packageName.startsWith('@vue/')
            ) {
              return 'vue-core'
            }

            if (packageName === 'page-agent' || packageName.startsWith('@page-agent/')) {
              return 'page-agent'
            }

            if (packageName === 'zod' || packageName.startsWith('@modelcontextprotocol/')) {
              return 'mcp'
            }

            if (
              packageName === 'naive-ui'
              || packageName === 'async-validator'
              || packageName === 'css-render'
              || packageName === 'date-fns'
              || packageName === 'date-fns-tz'
              || packageName === 'evtd'
              || packageName === 'seemly'
              || packageName === 'treemate'
              || packageName === 'vdirs'
              || packageName === 'vooks'
              || packageName === 'vueuc'
            ) {
              return 'naive-ui'
            }

            if (
              packageName === '@antv/g2plot'
            ) {
              return 'antv-g2plot'
            }

            if (
              packageName === '@antv/g2'
              || packageName === '@antv/component'
              || packageName === '@antv/scale'
              || packageName === '@antv/coord'
              || packageName === '@antv/adjust'
              || packageName === '@antv/attr'
              || packageName === '@antv/color-util'
              || packageName === '@antv/path-util'
              || packageName === '@antv/util'
              || packageName === 'd3-color'
              || packageName === 'd3-ease'
              || packageName === 'd3-hierarchy'
              || packageName === 'd3-interpolate'
              || packageName === 'd3-regression'
              || packageName === 'd3-timer'
              || packageName === 'fmin'
            ) {
              return 'antv-g2'
            }

            if (
              packageName === '@antv/x6'
              || packageName === '@antv/x6-common'
              || packageName === '@antv/x6-geometry'
              || packageName === '@antv/g-base'
              || packageName === '@antv/g-canvas'
              || packageName === '@antv/g-math'
              || packageName === '@antv/g-svg'
              || packageName === '@antv/matrix-util'
              || packageName === '@antv/dom-util'
              || packageName === '@antv/event-emitter'
              || packageName === 'gl-matrix'
            ) {
              return 'antv-x6'
            }

            if (
              packageName === 'highlight.js'
              || packageName === 'markdown-it'
              || packageName === 'markdown-it-highlightjs'
              || packageName === 'entities'
              || packageName === 'linkify-it'
              || packageName === 'mdurl'
              || packageName === 'prismjs'
              || packageName === 'uc.micro'
            ) {
              return 'markdown'
            }

            if (
              packageName === 'markmap-lib'
              || packageName === 'markmap-toolbar'
              || packageName === 'markmap-view'
            ) {
              return 'markmap'
            }

            if (packageName === 'three') {
              return 'three'
            }

            return 'vendor'
          },
        },
      },
    },
    css: {
      preprocessorOptions: {
        scss: {
          additionalData: `@use '@/styles/naive-variables.scss' as *;`,
        },
      },
    },
  }
})
