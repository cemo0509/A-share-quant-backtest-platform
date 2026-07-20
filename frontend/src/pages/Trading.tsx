import { useEffect, useState } from 'react'
import { Card, Typography, Button, Table, Statistic, Row, Col, Form, Input, Select, message, Spin } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { getAccount, getPositions, getOrders, placeOrder, resetAccount } from '../api'

const { Title, Text } = Typography
const { Option } = Select

interface Account {
  total_assets: number
  available_cash: number
  frozen_cash: number
  max_drawdown: number
  positions: Position[]
  orders: Order[]
}

interface Position {
  symbol: string
  quantity: number
  available_quantity: number
  cost_price: number
  current_price: number
  market_value: number
  profit_loss: number
  profit_loss_ratio: number
}

interface Order {
  order_id: string
  symbol: string
  action: string
  price: number
  quantity: number
  status: string
  filled_price: number
  filled_quantity: number
  created_at: string
}

export default function Trading() {
  const [account, setAccount] = useState<Account | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  // 获取账户信息
  const fetchAccount = async () => {
    setLoading(true)
    try {
      const res = await getAccount()
      setAccount(res.data.data || {})
    } catch {
      message.error('获取账户信息失败')
    } finally {
      setLoading(false)
    }
  }

  // 获取持仓信息
  const fetchPositions = async () => {
    try {
      const res = await getPositions()
      setPositions(res.data.data || [])
    } catch {
      message.error('获取持仓信息失败')
    }
  }

  // 获取订单历史
  const fetchOrders = async () => {
    try {
      const res = await getOrders()
      setOrders(res.data.data || [])
    } catch {
      message.error('获取订单历史失败')
    }
  }

  // 初始化数据
  useEffect(() => {
    fetchAccount()
    fetchPositions()
    fetchOrders()
  }, [])

  // 下单
  const handlePlaceOrder = async (values: any) => {
    try {
      const res = await placeOrder(values)
      if (res.data.status === 'ok') {
        message.success('下单成功')
        form.resetFields()
        // 刷新数据
        fetchAccount()
        fetchPositions()
        fetchOrders()
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '下单失败')
    }
  }

  // 重置账户
  const handleResetAccount = async () => {
    try {
      await resetAccount()
      message.success('账户重置成功')
      // 刷新数据
      fetchAccount()
      fetchPositions()
      fetchOrders()
    } catch (error) {
      message.error('重置账户失败')
    }
  }

  // 持仓表格列定义
  const positionColumns = [
    {
      title: '股票代码',
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: '持仓数量',
      dataIndex: 'quantity',
      key: 'quantity',
    },
    {
      title: '可用数量',
      dataIndex: 'available_quantity',
      key: 'available_quantity',
    },
    {
      title: '成本价',
      dataIndex: 'cost_price',
      key: 'cost_price',
      render: (price: number) => price.toFixed(2),
    },
    {
      title: '当前价',
      dataIndex: 'current_price',
      key: 'current_price',
      render: (price: number) => price.toFixed(2),
    },
    {
      title: '盈亏',
      dataIndex: 'profit_loss',
      key: 'profit_loss',
      render: (profit: number) => (
        <span style={{ color: profit >= 0 ? '#f5222d' : '#52c41a' }}>
          {profit.toFixed(2)}
        </span>
      ),
    },
  ]

  // 订单表格列定义
  const orderColumns = [
    {
      title: '订单ID',
      dataIndex: 'order_id',
      key: 'order_id',
    },
    {
      title: '股票代码',
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      render: (action: string) => (
        <span style={{ color: action === 'buy' ? '#f5222d' : '#52c41a' }}>
          {action === 'buy' ? '买入' : '卖出'}
        </span>
      ),
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (price: number) => price.toFixed(2),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        let color = 'black'
        if (status === 'filled') color = 'green'
        if (status === 'cancelled') color = 'orange'
        if (status === 'rejected') color = 'red'
        return <span style={{ color }}>{status}</span>
      },
    },
  ]

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div>
      <Title level={3}>交易管理</Title>
      
      {/* 账户信息 */}
      {account && (
        <Card style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="总资产" value={account.total_assets} precision={2} prefix="¥" />
            </Col>
            <Col span={6}>
              <Statistic title="可用资金" value={account.available_cash} precision={2} prefix="¥" />
            </Col>
            <Col span={6}>
              <Statistic title="冻结资金" value={account.frozen_cash} precision={2} prefix="¥" />
            </Col>
            <Col span={6}>
              <Button type="primary" danger onClick={handleResetAccount}>
                重置账户
              </Button>
            </Col>
          </Row>
        </Card>
      )}

      <Row gutter={16}>
        {/* 下单表单 */}
        <Col span={8}>
          <Card title="下单">
            <Form form={form} layout="vertical" onFinish={handlePlaceOrder}>
              <Form.Item
                label="股票代码"
                name="symbol"
                rules={[{ required: true, message: '请输入股票代码' }]}
              >
                <Input placeholder="如 000001" />
              </Form.Item>
              
              <Form.Item
                label="操作"
                name="action"
                rules={[{ required: true, message: '请选择操作' }]}
              >
                <Select placeholder="选择操作">
                  <Option value="buy">买入</Option>
                  <Option value="sell">卖出</Option>
                </Select>
              </Form.Item>
              
              <Form.Item
                label="数量"
                name="quantity"
                rules={[{ required: true, message: '请输入数量' }]}
              >
                <Input type="number" placeholder="如 100" />
              </Form.Item>
              
              <Form.Item
                label="价格"
                name="price"
                rules={[{ required: true, message: '请输入价格' }]}
              >
                <Input type="number" placeholder="如 10.5" />
              </Form.Item>
              
              <Form.Item>
                <Button type="primary" htmlType="submit" block>
                  下单
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </Col>

        {/* 持仓信息 */}
        <Col span={16}>
          <Card 
            title="持仓信息" 
            extra={
              <Button icon={<ReloadOutlined />} onClick={fetchPositions}>
                刷新
              </Button>
            }
          >
            <Table
              dataSource={positions}
              columns={positionColumns}
              rowKey="symbol"
              size="small"
              pagination={false}
            />
          </Card>
        </Col>
      </Row>

      {/* 订单历史 */}
      <Card 
        title="订单历史" 
        style={{ marginTop: 16 }}
        extra={
          <Button icon={<ReloadOutlined />} onClick={fetchOrders}>
            刷新
          </Button>
        }
      >
        <Table
          dataSource={orders}
          columns={orderColumns}
          rowKey="order_id"
          size="small"
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </div>
  )
}
