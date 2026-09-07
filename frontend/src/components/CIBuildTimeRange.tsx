import { useState } from 'react'
import { Button, Popover, Space, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'

const { Text } = Typography

export type CIBuildTimeRangeValue = {
  start: Dayjs
  end: Dayjs
  preset: string | null
}

const PRESETS = [
  { label: '3h', amount: 3, unit: 'hour' },
  { label: '6h', amount: 6, unit: 'hour' },
  { label: '12h', amount: 12, unit: 'hour' },
  { label: '24h', amount: 24, unit: 'hour' },
  { label: '7d', amount: 7, unit: 'day' },
  { label: '14d', amount: 14, unit: 'day' },
  { label: '30d', amount: 30, unit: 'day' },
  { label: '90d', amount: 90, unit: 'day' },
] as const

interface CIBuildTimeRangeProps {
  value: CIBuildTimeRangeValue
  onApply: (value: CIBuildTimeRangeValue) => void
}

function createDefaultBuildTimeRange(): CIBuildTimeRangeValue {
  const end = dayjs().endOf('day')
  return { start: end.subtract(13, 'day').startOf('day'), end, preset: '14d' }
}

function CIBuildTimeRange({ value, onApply }: CIBuildTimeRangeProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(value)

  const selectPreset = (preset: typeof PRESETS[number]) => {
    const end = dayjs()
    setDraft({ start: end.subtract(preset.amount, preset.unit), end, preset: preset.label })
  }

  const content = (
    <div className="ci-time-range-panel">
      <Space size={[8, 8]} wrap className="ci-time-range-presets">
        {PRESETS.map((preset) => (
          <Button key={preset.label} size="small"
            type={draft.preset === preset.label ? 'primary' : 'default'}
            onClick={() => selectPreset(preset)}>
            {preset.label}
          </Button>
        ))}
      </Space>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>From</Text>
          <input
            type="date"
            className="ci-time-range-date-input"
            value={draft.start.format('YYYY-MM-DD')}
            max={draft.end.format('YYYY-MM-DD')}
            onChange={(event) => setDraft({
              ...draft,
              start: dayjs(event.target.value).startOf('day'),
              preset: null,
            })}
          />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>To</Text>
          <input
            type="date"
            className="ci-time-range-date-input"
            value={draft.end.format('YYYY-MM-DD')}
            min={draft.start.format('YYYY-MM-DD')}
            max={dayjs().format('YYYY-MM-DD')}
            onChange={(event) => setDraft({
              ...draft,
              end: dayjs(event.target.value).endOf('day'),
              preset: null,
            })}
          />
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button size="small" onClick={() => setDraft(createDefaultBuildTimeRange())}>Reset</Button>
        <Button size="small" type="primary" disabled={!draft.start.isBefore(draft.end)}
          onClick={() => { onApply(draft); setOpen(false) }}>
          Apply
        </Button>
      </div>
    </div>
  )

  return (
    <div style={{ width: 260 }}>
      <Text type="secondary" strong style={{ fontSize: 12 }}>Time Range</Text>
      <Popover open={open} trigger="click" placement="bottomRight" content={content}
        overlayClassName="ci-time-range-popover"
        onOpenChange={(nextOpen) => { setOpen(nextOpen); if (nextOpen) setDraft(value) }}>
        <Button block style={{ textAlign: 'left' }}>
          {value.preset?.endsWith('h')
            ? `Last ${value.preset}`
            : `${value.start.format('YYYY-MM-DD')} — ${value.end.format('YYYY-MM-DD')}`}
        </Button>
      </Popover>
    </div>
  )
}

export default CIBuildTimeRange
