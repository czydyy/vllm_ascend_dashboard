import { useMemo, useState } from 'react'
import { Card, Empty, Segmented, Typography } from 'antd'
import {
  Bar,
  BarChart,
  Area,
  ComposedChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { CIResult } from '../services/ci'
import {
  buildDailyDurationOverview,
  buildDurationAxis,
  buildRunDurationPoints,
  type BuildRunDurationPoint,
  type BuildDailyDurationPoint,
} from '../utils/ciBuildStats'

const { Text, Title } = Typography

type ChartMode = 'runs' | 'overview'

interface CIBuildDurationChartProps {
  runs: CIResult[]
  loading: boolean
}

function formatDuration(minutes: number): string {
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    const remainder = Math.round(minutes % 60)
    return remainder ? `${hours}小时${remainder}分钟` : `${hours}小时`
  }
  return `${Math.round(minutes)}分钟`
}

function formatDurationAxis(minutes: number): string {
  return `${Math.round(minutes / 60)}h`
}

function BuildRunTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: ReadonlyArray<{ payload?: BuildRunDurationPoint }>
}) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null

  const status = point.failed ? 'Failed' : 'Passed'
  const statusColor = point.failed ? '#ff4d4f' : '#00a76f'

  return (
    <div style={{ minWidth: 260, background: '#fff', border: '1px solid #d9d9d9', borderRadius: 10, padding: '14px 16px', boxShadow: '0 6px 18px rgba(0, 0, 0, 0.12)' }}>
      <div style={{ color: statusColor, fontWeight: 600, marginBottom: 12 }}>{status}</div>
      <div style={{ color: '#344054', marginBottom: 8 }}>{point.tooltipLabel}</div>
      <div style={{ color: '#344054' }}>Build duration：{formatDuration(point.durationMinutes)}</div>
    </div>
  )
}

function BuildOverviewTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: ReadonlyArray<{ payload?: BuildDailyDurationPoint }>
}) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null

  const date = new Date(`${point.dateKey}T00:00:00`)
  const dateLabel = date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })

  return (
    <div style={{ minWidth: 260, background: '#fff', border: '1px solid #d9d9d9', borderRadius: 10, padding: '14px 16px', boxShadow: '0 6px 18px rgba(0, 0, 0, 0.12)' }}>
      <div style={{ color: '#101828', fontWeight: 600, marginBottom: 12 }}>{dateLabel}</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '8px 20px' }}>
        <span style={{ color: '#667085' }}>Typical (P50)</span>
        <strong style={{ color: '#1677ff' }}>{formatDuration(point.p50)}</strong>
        <span style={{ color: '#667085' }}>High (P90)</span>
        <strong style={{ color: '#fa8c16' }}>{formatDuration(point.p90)}</strong>
        <span style={{ color: '#667085' }}>Peak</span>
        <strong style={{ color: '#722ed1' }}>{formatDuration(point.peak)}</strong>
      </div>
      <div style={{ borderTop: '1px solid #eaecf0', marginTop: 12, paddingTop: 10, display: 'flex', gap: 16 }}>
        <strong style={{ color: '#00a76f' }}>{point.passed} passed</strong>
        <strong style={{ color: '#ff4d4f' }}>{point.failed} failed</strong>
        <strong style={{ color: '#475467', marginLeft: 'auto' }}>{Math.round(point.passRate)}%</strong>
      </div>
    </div>
  )
}

function CIBuildDurationChart({ runs, loading }: CIBuildDurationChartProps) {
  const [mode, setMode] = useState<ChartMode>('runs')
  const runPoints = useMemo(() => buildRunDurationPoints(runs), [runs])
  const overviewPoints = useMemo(() => buildDailyDurationOverview(runPoints), [runPoints])
  const chartData = mode === 'runs' ? runPoints : overviewPoints
  const runAxis = useMemo(
    () => buildDurationAxis(Math.max(0, ...runPoints.map((point) => point.durationMinutes))),
    [runPoints],
  )
  const overviewAxis = useMemo(
    () => buildDurationAxis(Math.max(0, ...overviewPoints.map((point) => point.p90))),
    [overviewPoints],
  )
  const firstDate = runPoints[0]?.dateLabel
  const lastDate = runPoints[runPoints.length - 1]?.dateLabel

  return (
    <Card
      loading={loading}
      style={{ marginBottom: 24 }}
      styles={{ body: { paddingTop: 20 } }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 20 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Build Duration</Title>
          <Text type="secondary">
            {firstDate && lastDate
              ? `${firstDate} — ${lastDate} · ${runPoints.length} builds`
              : '暂无构建时长数据'}
          </Text>
        </div>
        <Segmented
          value={mode}
          onChange={(value) => setMode(value as ChartMode)}
          options={[{ label: 'Runs', value: 'runs' }, { label: 'Overview', value: 'overview' }]}
        />
      </div>

      {chartData.length === 0 ? (
        <Empty description="暂无构建时长数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <ResponsiveContainer width="100%" height={360}>
          {mode === 'runs' ? (
            <BarChart data={runPoints} barCategoryGap={0}>
              <CartesianGrid strokeDasharray="4 4" vertical={false} />
              <XAxis dataKey="timestamp" minTickGap={55} tick={{ fontSize: 12 }} />
              <YAxis domain={[0, runAxis.maxMinutes]} ticks={runAxis.ticks} tickFormatter={formatDurationAxis} width={52} allowDataOverflow />
              <Tooltip content={<BuildRunTooltip />} />
              <Bar dataKey="durationMinutes" name="Build duration" minPointSize={2}>
                {runPoints.map((point) => (
                  <Cell key={point.id} fill={point.failed ? '#ff4d4f' : '#00b96b'} />
                ))}
              </Bar>
            </BarChart>
          ) : (
            <ComposedChart data={overviewPoints}>
              <CartesianGrid strokeDasharray="4 4" vertical={false} />
              <XAxis dataKey="dateLabel" minTickGap={30} tick={{ fontSize: 12 }} />
              <YAxis yAxisId="duration" domain={[0, overviewAxis.maxMinutes]} ticks={overviewAxis.ticks} tickFormatter={formatDurationAxis} width={52} allowDataOverflow />
              <YAxis yAxisId="rate" orientation="right" domain={[0, 100]} tickFormatter={(value: number) => `${value}%`} width={50} />
              <Tooltip content={<BuildOverviewTooltip />} />
              <Legend />
              <Area type="monotone" yAxisId="duration" dataKey="p50" stackId="duration-range" name="Typical (P50)" stroke="none" fill="transparent" legendType="none" />
              <Area type="monotone" yAxisId="duration" dataKey="p50ToP90" stackId="duration-range" name="P50–P90 range" stroke="none" fill="#1677ff" fillOpacity={0.14} />
              <Line type="monotone" yAxisId="duration" dataKey="p50" name="Typical (P50)" stroke="#1677ff" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 5 }} />
              <Line type="monotone" yAxisId="duration" dataKey="p90" name="High (P90)" stroke="#fa8c16" strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
              <Line type="monotone" yAxisId="rate" dataKey="passRate" name="Pass rate" stroke="#00b96b" strokeWidth={2} strokeDasharray="6 5" dot={{ r: 3 }} activeDot={{ r: 5 }} />
            </ComposedChart>
          )}
        </ResponsiveContainer>
      )}
    </Card>
  )
}

export default CIBuildDurationChart
