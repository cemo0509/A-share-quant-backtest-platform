import { useState, useEffect } from 'react';
import { Card, Row, Col, Table, Spin, Alert, Button, Typography, Statistic } from 'antd';
import { LineChartOutlined, TableOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import type { BacktestResult } from '../services/api';
import { useStore, resolveDark } from '../stores';

const { Title, Paragraph, Text } = Typography;

interface BacktestResultPageProps {
  result?: BacktestResult;
  loading?: boolean;
}

const BacktestResultPage: React.FC<BacktestResultPageProps> = ({ result, loading }) => {
  const [equityChartRef, setEquityChartRef] = useState<HTMLDivElement | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const mode = useStore((s) => s.mode);
  const isDark = resolveDark(mode);

  // 初始化资金曲线图
  useEffect(() => {
    if (equityChartRef && result?.equity_curve) {
      const chart = echarts.init(equityChartRef, isDark ? 'dark' : undefined);
      const dates = result.equity_curve.map((item: any) => item.date);
      const values = result.equity_curve.map((item: any) => item.value);

      chart.setOption({
        title: { text: '资金曲线', left: 'center' },
        xAxis: { type: 'category', data: dates },
        yAxis: { type: 'value' },
        series: [{
          data: values,
          type: 'line',
          smooth: true,
          areaStyle: { opacity: 0.3 },
          lineStyle: { color: '#1890ff', width: 2 },
          itemStyle: { color: '#1890ff' },
        }],
        tooltip: {
          trigger: 'axis',
          formatter: (params: any) => {
            const param = params[0];
            return `日期: ${param.name}<br/>资金: ${param.value.toFixed(2)}`;
          },
        },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      });

      return () => chart.dispose();
    }
  }, [equityChartRef, result, isDark]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" />
        <p style={{ marginTop: 16 }}>回测中，请稍候...</p>
      </div>
    );
  }

  if (!result) {
    return (
      <Alert
        message="暂无回测结果"
        description="请先在回测页面运行回测"
        type="info"
        showIcon
        style={{ margin: 24 }}
      />
    );
  }

  const tradeColumns = [
    { title: '交易ID', dataIndex: 'id', key: 'id' },
    { title: '入场日期', dataIndex: 'entry_date', key: 'entry_date' },
    { title: '入场价格', dataIndex: 'entry_price', key: 'entry_price', render: (v: number) => v.toFixed(2) },
    { title: '出场日期', dataIndex: 'exit_date', key: 'exit_date' },
    { title: '出场价格', dataIndex: 'exit_price', key: 'exit_price', render: (v: number) => v.toFixed(2) },
    {
      title: '收益率%',
      dataIndex: 'return_pct',
      key: 'return_pct',
      render: (v: number) => (
        <Text type={v >= 0 ? 'success' : 'danger'}>{v.toFixed(2)}%</Text>
      ),
    },
    { title: '持仓天数', dataIndex: 'hold_days', key: 'hold_days' },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>回测结果</Title>

      {/* 绩效指标卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总收益率"
              value={result.total_return}
              precision={2}
              suffix="%"
              valueStyle={{ color: result.total_return >= 0 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="年化收益率"
              value={result.annual_return ?? 0}
              precision={2}
              suffix="%"
              valueStyle={{ color: (result.annual_return ?? 0) >= 0 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="最大回撤"
              value={result.max_drawdown}
              precision={2}
              suffix="%"
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="夏普比率"
              value={result.sharpe_ratio}
              precision={3}
              valueStyle={{ color: result.sharpe_ratio >= 1 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="胜率"
              value={result.win_rate}
              precision={2}
              suffix="%"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="交易次数"
              value={result.total_trades}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="最终资金"
              value={result.final_value}
              precision={2}
              prefix="¥"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Button
              type="primary"
              icon={<TableOutlined />}
              onClick={() => setShowDetails(!showDetails)}
              block
            >
              {showDetails ? '隐藏详情' : '显示详情'}
            </Button>
          </Card>
        </Col>
      </Row>

      {/* 资金曲线图 */}
      <Card title="资金曲线" style={{ marginBottom: 24 }}>
        <div ref={setEquityChartRef} style={{ width: '100%', height: 400 }} />
      </Card>

      {/* 交易明细 */}
      {showDetails && (
        <Card title="交易明细" style={{ marginBottom: 24 }}>
          <Table
            columns={tradeColumns}
            dataSource={result.trades || []}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 800 }}
          />
        </Card>
      )}

      {/* K线图 + 买卖点（待实现） */}
      <Card title="K线图 + 买卖点" style={{ marginBottom: 24 }}>
        <Alert
          message="功能开发中"
          description="K线图和买卖点标记功能将在后续版本中提供"
          type="info"
          showIcon
        />
      </Card>
    </div>
  );
};

export default BacktestResultPage;
