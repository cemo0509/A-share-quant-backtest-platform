import { useEffect, useState } from 'react'
import { Card, Col, Row, Typography, Tag, Spin } from 'antd'
import { Link } from 'react-router-dom'
import api from '../api'

const { Title, Paragraph } = Typography

const features = [
  { title: '历史回测', desc: '基于 Backtrader 事件驱动引擎，支持日K/分钟K回测', link: '/backtest' },
  { title: '预置策略', desc: '双均线、布林带、RSI、MACD 经典策略开箱即用', link: '/strategy' },
  { title: '数据管理', desc: 'AKShare 免费 A 股数据，Parquet 本地缓存', link: '/data' },
  { title: '结果可视化', desc: 'K线、资金曲线、交易明细、回测指标全景展示', link: '/results' },
]

export default function Dashboard() {
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking')

  useEffect(() => {
    api
      .get('/health')
      .then(() => setBackendStatus('online'))
      .catch(() => setBackendStatus('offline'))
  }, [])

  return (
    <div>
      <Title level={2}>A股量化回测平台</Title>
      <Paragraph type="secondary">
        面向 A 股市场的桌面端量化回测与策略开发平台。技术栈：Backtrader + FastAPI + React + Electron
      </Paragraph>
      <div style={{ marginBottom: 16 }}>
        后端状态：
        {backendStatus === 'checking' ? (
          <Spin size="small" style={{ marginLeft: 8 }} />
        ) : backendStatus === 'online' ? (
          <Tag color="green">在线</Tag>
        ) : (
          <Tag color="red">离线 — 请先启动后端</Tag>
        )}
      </div>
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        {features.map((f) => (
          <Col span={12} key={f.title}>
            <Link to={f.link}>
              <Card hoverable title={f.title}>
                <Paragraph>{f.desc}</Paragraph>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>
    </div>
  )
}
