import childRoutes from '@/router/child-routes'
import Login from '../views/Login.vue'

const routes: Array<RouteRecordRaw> = [
    {
        path: '/',
        name: 'Root',
        redirect: {
            name: 'ChatRoot'
        },
        meta: { requiresAuth: true } // 标记需要认证
    },
    ...childRoutes,
    {
        path: '/:pathMatch(.*)',
        name: '404',
        component: () => import('@/components/404.vue')
    },
    {
        path: '/login',
        name: 'Login',
        component: Login
    }
]

export default routes
