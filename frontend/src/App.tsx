import { Suspense, lazy } from 'react'
import { HashRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Layout, Menu, Skeleton, theme, ConfigProvider, Segmented, Tooltip } from 'antd'
import {
  DashboardOutlined,
  ExperimentOutlined,
  CodeOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  LineChartOutlined,
  SwapOutlined,
  AimOutlined,
  FilterOutlined,
  RadarChartOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BulbOutlined,
  BulbFilled,
  DesktopOutlined,
} from '@ant-design/icons'
import ErrorBoundary from './components/ErrorBoundary'
import { useStore, resolveDark } from './stores'
import zhCN from 'antd/locale/zh_CN'

// 路由级代码分割：重型页面按需加载，减少初始 chunk 体积
// 同时保存 import 函数引用，用于悬停/空闲预加载（消除跳转白屏）
const pages = {
  Dashboard: () => import('./pages/Dashboard'),
  Backtest: () => import('./pages/Backtest'),
  StrategyEditor: () => import('./pages/StrategyEditor'),
  DataManage: () => import('./pages/DataManage'),
  Results: () => import('./pages/Results'),
  RealtimeQuotes: () => import('./components/RealtimeQuotes'),
  Trading: () => import('./pages/Trading'),
  Optimize: () => import('./pages/Optimize'),
  Compare: () => import('./pages/Compare'),
  StockScan: () => import('./pages/StockScan'),
  StockDetail: () => import('./pages/StockDetail'),
  RealtimePool: () => import('./pages/RealtimePool'),
}
const Dashboard = lazy(pages.Dashboard)
const Backtest = lazy(pages.Backtest)
const StrategyEditor = lazy(pages.StrategyEditor)
const DataManage = lazy(pages.DataManage)
const Results = lazy(pages.Results)
const RealtimeQuotes = lazy(pages.RealtimeQuotes)
const Trading = lazy(pages.Trading)
const Optimize = lazy(pages.Optimize)
const Compare = lazy(pages.Compare)
const StockScan = lazy(pages.StockScan)
const StockDetail = lazy(pages.StockDetail)
const RealtimePool = lazy(pages.RealtimePool)

// 路由 → 预加载函数映射（菜单 key 与页面 key 对应，StockDetail 按需预加载）
const routePreload: Record<string, () => Promise<any>> = {
  '/': pages.Dashboard,
  '/backtest': pages.Backtest,
  '/stock-scan': pages.StockScan,
  '/realtime-pool': pages.RealtimePool,
  '/optimize': pages.Optimize,
  '/compare': pages.Compare,
  '/strategy': pages.StrategyEditor,
  '/data': pages.DataManage,
  '/results': pages.Results,
  '/realtime': pages.RealtimeQuotes,
  '/trading': pages.Trading,
}

// 空闲时预加载所有页面（requestIdleCallback 兜底 setTimeout），避免首次跳转卡顿
const preloadAll = () => {
  const preload = () => Object.values(pages).forEach((fn) => { try { fn() } catch { /* 忽略预加载错误 */ } })
  if ('requestIdleCallback' in window) {
    (window as any).requestIdleCallback(preload, { timeout: 3000 })
  } else {
    setTimeout(preload, 1500)
  }
}

/** 页面加载时的骨架屏，替代白屏转圈，体感更快 */
function PageLoader() {
  return (
    <div style={{ padding: 8 }}>
      <Skeleton active paragraph={{ rows: 6 }} title={{ width: '30%' }} />
      <div style={{ marginTop: 24 }}>
        <Skeleton active paragraph={{ rows: 4 }} title={{ width: '40%' }} />
      </div>
    </div>
  )
}

const { Sider, Content, Header } = Layout

// 菜单按业务分组，信息密度更高、更易定位
const menuItems = [
  {
    type: 'group' as const,
    label: '总览',
    children: [
      { key: '/', icon: <DashboardOutlined />, label: '首页' },
    ],
  },
  {
    type: 'group' as const,
    label: '回测分析',
    children: [
      { key: '/backtest', icon: <ExperimentOutlined />, label: '回测' },
      { key: '/compare', icon: <SwapOutlined />, label: '策略比较' },
      { key: '/optimize', icon: <AimOutlined />, label: '参数优化' },
      { key: '/results', icon: <BarChartOutlined />, label: '回测结果' },
    ],
  },
  {
    type: 'group' as const,
    label: '策略',
    children: [
      { key: '/strategy', icon: <CodeOutlined />, label: '策略编辑' },
    ],
  },
  {
    type: 'group' as const,
    label: '选股与行情',
    children: [
      { key: '/stock-scan', icon: <FilterOutlined />, label: '选股池' },
      { key: '/realtime-pool', icon: <RadarChartOutlined />, label: '实时选股池' },
      { key: '/realtime', icon: <LineChartOutlined />, label: '实时行情' },
    ],
  },
  {
    type: 'group' as const,
    label: '数据与交易',
    children: [
      { key: '/data', icon: <DatabaseOutlined />, label: '数据管理' },
      { key: '/trading', icon: <SwapOutlined />, label: '交易管理' },
    ],
  },
]

function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()
  const [collapsed, setCollapsed] = useState(false)
  const mode = useStore((s) => s.mode)
  const setMode = useStore((s) => s.setMode)
  const isDark = resolveDark(mode)

  // 空闲预加载所有路由 chunk，消除首次跳转白屏
  useEffect(() => { preloadAll() }, [])

  const handleMenuClick = (key: string) => {
    // 点击菜单时若该页面尚未加载，先触发预加载再跳转（多数情况已在空闲时加载完）
    routePreload[key]?.()
    navigate(key)
  }

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider
        width={208}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme={isDark ? 'dark' : 'light'}
        trigger={null}
      >
        <div style={{
          height: 56,
          color: isDark ? '#fff' : token.colorText,
          textAlign: 'center',
          lineHeight: '56px',
          fontWeight: 700,
          fontSize: collapsed ? 14 : 16,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        }}>
          {collapsed ? '量化的' : '量化回测平台'}
        </div>
        <Menu
          theme={isDark ? 'dark' : 'light'}
          mode="inline"
          items={menuItems}
          selectedKeys={[location.pathname]}
          onClick={({ key }) => handleMenuClick(key)}
        />
      </Sider>
      <Layout>
        <Header style={{
          padding: '0 16px',
          background: token.colorBgContainer,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
        }}>
          <span
            onClick={() => setCollapsed(!collapsed)}
            style={{ cursor: 'pointer', fontSize: 18, color: token.colorText }}
            aria-label="切换侧边栏"
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </span>
          <Tooltip title="主题：浅色 / 深色 / 跟随系统">
            <Segmented
              value={mode}
              onChange={(v) => setMode(v as 'dark' | 'light' | 'system')}
              options={[
                { label: '浅色', value: 'light', icon: <BulbOutlined /> },
                { label: '深色', value: 'dark', icon: <BulbFilled /> },
                { label: '跟随系统', value: 'system', icon: <DesktopOutlined /> },
              ]}
            />
          </Tooltip>
        </Header>
        <Content style={{ overflow: 'auto', padding: 24, background: token.colorBgLayout }}>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/backtest" element={<Backtest />} />
              <Route path="/stock-scan" element={<StockScan />} />
              <Route path="/realtime-pool" element={<RealtimePool />} />
              <Route path="/stock/:symbol" element={<StockDetail />} />
              <Route path="/optimize" element={<Optimize />} />
              <Route path="/compare" element={<Compare />} />
              <Route path="/strategy" element={<StrategyEditor />} />
              <Route path="/data" element={<DataManage />} />
              <Route path="/results" element={<Results />} />
              <Route path="/realtime" element={<RealtimeQuotes />} />
              <Route path="/trading" element={<Trading />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  )
}

export default function App() {
  const mode = useStore((s) => s.mode)
  const isDark = resolveDark(mode)
  return (
    <ErrorBoundary>
      <ConfigProvider
        locale={zhCN}
        theme={{ algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm }}
      >
        <HashRouter>
          <AppLayout />
        </HashRouter>
      </ConfigProvider>
    </ErrorBoundary>
  )
}
