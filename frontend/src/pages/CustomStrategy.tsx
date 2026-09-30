import { useEffect, useState } from 'react'
import { Button, Card, Empty, Input, Modal, Space, Tag, Typography, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { listVisualRules } from '../api'
import VisualEditor from '../components/visual-editor/VisualEditor'

const { Title, Paragraph, Text } = Typography

const KEY_RE = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/

/** 页面 B：自定义策略 —— 自由组合指标条件造新策略。
 *
 * 编辑器本体直接复用 VisualEditor（指标库 + 条件标签块 + 生成代码 + 立即回测），
 * 这里只负责「新建 / 选择已有规则」的外壳，避免在两处维护同一套编辑逻辑。
 */
export default function CustomStrategy() {
  const [rules, setRules] = useState<Array<{ key: string; name?: string; description?: string }>>([])
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [newOpen, setNewOpen] = useState(false)
  const [newKey, setNewKey] = useState('')

  const loadRules = () => {
    listVisualRules()
      .then((r: any) => {
        const list = (r.data.data || []) as Array<{ key: string; name?: string; description?: string }>
        setRules(list)
        if (!selectedKey && list.length > 0) setSelectedKey(list[0].key)
      })
      .catch(() => message.warning('自定义策略列表加载失败'))
  }

  useEffect(() => {
    loadRules()
  }, [])

  // 切换规则：只改 key，编辑器内容由 VisualEditor 内部按 key 重新加载，
  // 不会带上一条规则的内容。
  const selectedName = rules.find((r) => r.key === selectedKey)?.name || ''

  const handleCreate = () => {
    const key = newKey.trim()
    if (!key) {
      message.warning('请输入策略 key')
      return
    }
    if (!KEY_RE.test(key)) {
      message.warning('key 只能包含字母、数字、下划线和连字符，且以字母开头')
      return
    }
    if (rules.some((r) => r.key === key)) {
      message.warning('已存在同名的自定义策略')
      return
    }
    setNewOpen(false)
    setNewKey('')
    setSelectedKey(key)
    message.info(`已新建「${key}」，请在下方添加条件并保存`)
  }

  return (
    <div>
      <Title level={3}>自定义策略</Title>
      <Paragraph type="secondary">
        自由组合指标条件创建新策略：添加条件 → 取名 → 保存。保存后的策略会进入策略列表，
        可以像预置策略一样被选择、回测。
      </Paragraph>

      <Card
        size="small"
        title="我的自定义策略"
        style={{ marginBottom: 12 }}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setNewOpen(true)}>
            新建策略
          </Button>
        }
      >
        {rules.length === 0 ? (
          <Empty description="还没有自定义策略，点右上角「新建策略」开始" />
        ) : (
          <Space wrap>
            {rules.map((r) => (
              <Button
                key={r.key}
                type={selectedKey === r.key ? 'primary' : 'default'}
                onClick={() => setSelectedKey(r.key)}
              >
                {r.name || r.key}
              </Button>
            ))}
            {!selectedKey && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                （未选中：可从上方选一条已有策略，或新建）
              </Text>
            )}
          </Space>
        )}
      </Card>

      {rules.length > 0 && selectedKey && (
        <div style={{ marginBottom: 8 }}>
          <Tag color="purple">当前编辑：{selectedKey}</Tag>
        </div>
      )}

      <div style={{ height: 'calc(100vh - 330px)', border: '1px solid #f0f0f0', borderRadius: 6 }}>
        <VisualEditor
          ruleKey={selectedKey}
          ruleName={selectedName}
          onSaved={loadRules}
          onKeyChange={(k) => {
            setSelectedKey(k)
            loadRules()
          }}
        />
      </div>

      <Modal
        title="新建自定义策略"
        open={newOpen}
        onCancel={() => setNewOpen(false)}
        onOk={handleCreate}
        okText="创建"
        cancelText="取消"
      >
        <div style={{ marginBottom: 4 }}>策略 key（字母开头，可含数字/下划线/连字符）</div>
        <Input
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          placeholder="如 my_factor_rule"
          onPressEnter={handleCreate}
        />
        <div style={{ marginTop: 8, fontSize: 12 }} className="secondary">
          创建后在下方的编辑器里添加条件，填好策略名称再点「保存策略」。
        </div>
      </Modal>
    </div>
  )
}
