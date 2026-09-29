import { useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Drawer, Modal, Row, Segmented, Select, Space, Statistic, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  type OccupancyDimension,
  type OccupancyRange,
  type OccupancyTask,
  type OccupancyView,
  getMockOccupancyTimeline,
  getMockTasks,
  mockPools,
  mockProjects,
  mockRawTask,
} from '../services/npuOccupancy'
import CIBuildTimeRange, { type CIBuildTimeRangeValue } from '../components/CIBuildTimeRange'

const { Text } = Typography

const formatCards = (value: number) => `${Math.round(value)} 卡`

function OccupancyTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 12px', minWidth: 180 }}>
      <Text strong>{dayjs(label).format('MM-DD HH:mm')}</Text>
      {payload.map((entry: any) => (
        <div key={entry.dataKey} style={{ color: entry.color, marginTop: 4, fontSize: 12 }}>{entry.name}：{formatCards(entry.value)}</div>
      ))}
    </div>
  )
}

export default function NpuOccupancyTrend() {
  const [view, setView] = useState<OccupancyView>('pool')
  const [timeRange, setTimeRange] = useState<CIBuildTimeRangeValue>(() => {
    const end = dayjs()
    return { start: end.subtract(24, 'hour'), end, preset: '24h' }
  })
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [drillTime, setDrillTime] = useState<string | null>(null)
  const [drillMode, setDrillMode] = useState<'project' | 'pool'>('project')
  const [rawTask, setRawTask] = useState<OccupancyTask | null>(null)

  const dimensions = view === 'pool' ? mockPools : mockProjects
  const selected = selectedIds.length ? selectedIds : dimensions.map(item => item.id)
  const range: OccupancyRange = timeRange.preset === '1h' || timeRange.preset === '24h' || timeRange.preset === '7d' || timeRange.preset === '30d' ? timeRange.preset : 'custom'
  const customRangeValues: [string, string] = [timeRange.start.toISOString(), timeRange.end.toISOString()]
  const points = useMemo(() => getMockOccupancyTimeline(view, range, customRangeValues), [view, range, customRangeValues])
  const chartData = useMemo(() => points.map(point => {
    const values = Object.fromEntries(selected.map(id => [id, point.values[id] ?? 0]))
    return { time: point.time, label: dayjs(point.time).format(range === '30d' ? 'MM-DD' : 'MM-DD HH:mm'), ...values, total: Object.values(values).reduce((sum, value) => sum + Number(value), 0) }
  }), [points, range, selected])
  const values = chartData.map(row => row.total)
  const peak = Math.max(...values, 0)
  const average = values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1)
  const end = values[values.length - 1] ?? 0
  const capacity = view === 'pool' ? dimensions.filter(item => selected.includes(item.id)).reduce((sum, item) => sum + (item.capacity ?? 0), 0) : undefined
  const tasks = drillTime ? getMockTasks(drillTime).filter(task => {
    if (!selectedIds.length) return true
    const name = view === 'pool' ? task.pool : task.project
    return dimensions.filter(item => selected.includes(item.id)).some(item => name.includes(item.name.split(' ')[0]) || name === item.name)
  }) : []
  const groupedTasks = useMemo(() => tasks.reduce<Record<string, OccupancyTask[]>>((groups, task) => {
    const key = drillMode === 'project' ? task.project : task.pool
    groups[key] = [...(groups[key] ?? []), task]
    return groups
  }, {}), [drillMode, tasks])

  const changeView = (next: OccupancyView) => {
    setView(next)
    setSelectedIds([])
    setDrillTime(null)
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Alert type="info" showIcon message="演示原型" description="当前页使用本地模拟数据，仅用于确认页面结构、筛选和下钻交互；尚未连接 pod-history-api、数据库或定时采集任务。" />

      <Card size="small">
        <Row gutter={[16, 16]} align="middle">
          <Col>
            <Segmented value={view} options={[{ label: '按资源池', value: 'pool' }, { label: '按项目', value: 'project' }]} onChange={value => changeView(value as OccupancyView)} />
          </Col>
          <Col flex="auto">
            <Select mode="multiple" allowClear maxTagCount="responsive" value={selectedIds} onChange={setSelectedIds} placeholder={`${view === 'pool' ? '资源池' : '项目 / 社区'}（留空为合计）`} style={{ width: '100%' }} options={dimensions.map(item => ({ value: item.id, label: item.capacity ? `${item.name} · ${item.capacity} 卡` : item.name }))} />
          </Col>
        </Row>
        <div style={{ marginTop: 16 }}><CIBuildTimeRange value={timeRange} onApply={setTimeRange} /></div>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}><Card size="small"><Statistic title="当前范围峰值占用" value={peak} suffix="卡" valueStyle={{ color: '#1677ff' }} /><Text type="secondary">模拟序列中的最高值</Text></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card size="small"><Statistic title="当前范围平均占用" value={average} precision={1} suffix="卡" /><Text type="secondary">按采样点平均</Text></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card size="small"><Statistic title="范围末时刻占用" value={end} suffix="卡" valueStyle={{ color: '#13c2c2' }} /><Text type="secondary">{dayjs(chartData[chartData.length - 1]?.time).format('MM-DD HH:mm')}</Text></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card size="small"><Statistic title={view === 'pool' ? '当前口径逻辑卡数' : '范围内模拟申请'} value={capacity ?? 24} suffix={capacity ? '卡' : '条'} /><Text type="secondary">{capacity ? `峰值占比 ${Math.round(peak / capacity * 100)}%` : '项目不设专属容量线'}</Text></Card></Col>
      </Row>

      <Card title="NPU 卡占用存量趋势" extra={<Text type="secondary">点击曲线中的时刻查看占用明细</Text>}>
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>纵轴为该时刻已占用的 NPU 卡数。{view === 'pool' ? '虚线为所选资源池逻辑卡数。' : '项目视图不显示容量线，避免将全池容量误用为项目容量。'}</Text>
        <ResponsiveContainer width="100%" height={370}>
          <LineChart data={chartData} onClick={(state: any) => state?.activePayload?.[0]?.payload?.time && setDrillTime(state.activePayload[0].payload.time)}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" minTickGap={48} tick={{ fontSize: 12 }} />
            <YAxis label={{ value: '占用卡数', angle: -90, position: 'insideLeft' }} allowDecimals={false} />
            <Tooltip content={<OccupancyTooltip />} />
            <Legend />
            {capacity ? <ReferenceLine y={capacity} stroke="#fa8c16" strokeDasharray="6 4" label={{ value: `逻辑容量 ${capacity} 卡`, position: 'insideTopRight', fill: '#ad6800', fontSize: 12 }} /> : null}
            {selectedIds.length > 1 || selectedIds.length === 0 ? <Line type="monotone" dataKey="total" name="合计占用" stroke="#1677ff" strokeWidth={3} dot={false} activeDot={{ r: 5 }} /> : dimensions.filter(item => selected.includes(item.id)).map(item => <Line key={item.id} type="monotone" dataKey={item.id} name={item.name} stroke={item.color} strokeWidth={3} dot={false} activeDot={{ r: 5 }} />)}
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Drawer width={820} title={`占用明细 · ${drillTime ? dayjs(drillTime).format('YYYY-MM-DD HH:mm') : ''}`} open={Boolean(drillTime)} onClose={() => setDrillTime(null)}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Alert type="warning" showIcon message="演示明细" description="任务数据为本地模拟数据；真实接入后将按当前时刻和筛选条件查询。" />
          <Segmented value={drillMode} options={[{ label: '按社区', value: 'project' }, { label: '按资源池', value: 'pool' }]} onChange={value => setDrillMode(value as 'project' | 'pool')} />
          {Object.entries(groupedTasks).map(([name, group]) => (
            <section key={name} style={{ borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
              <Space size={8} style={{ marginBottom: 12 }}><Text strong>{name}</Text><Tag color="blue">{group.reduce((sum, task) => sum + task.cards, 0)} 卡</Tag><Text type="secondary">{group.length} 条任务</Text></Space>
              <Space direction="vertical" size={14} style={{ width: '100%' }}>
                {group.map(task => (
                  <div key={task.id} style={{ padding: '0 0 14px', borderBottom: '1px solid #f5f5f5' }}>
                    <Text strong style={{ display: 'block' }}>{task.workflow}</Text>
                    <Space direction="vertical" size={2} style={{ marginTop: 6, alignItems: 'flex-start' }}>
                      <Text>{task.cards} 卡</Text>
                      <Text>{task.node} <Text type="secondary">· NPU {task.npuList}</Text></Text>
                      <Tag color={task.status === 'active' ? 'green' : 'default'} style={{ marginInlineEnd: 0 }}>{task.status}</Tag>
                      <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setRawTask(task)}>查看原始 JSON</Button>
                    </Space>
                  </div>
                ))}
              </Space>
            </section>
          ))}
        </Space>
      </Drawer>

      <Modal title={`原始 JSON · ${rawTask?.id ?? ''}`} open={Boolean(rawTask)} onCancel={() => setRawTask(null)} footer={<Button onClick={() => setRawTask(null)}>关闭</Button>} width={780}>
        <Alert type="info" showIcon message="演示数据" description="真实接入后，这里将受权限控制并展示对应 env_id 的原始 API 记录。" style={{ marginBottom: 16 }} />
        <pre style={{ maxHeight: 420, overflow: 'auto', padding: 12, borderRadius: 6, background: '#f6f8fa', fontSize: 12 }}>{rawTask ? JSON.stringify(mockRawTask(rawTask), null, 2) : ''}</pre>
      </Modal>
    </Space>
  )
}
