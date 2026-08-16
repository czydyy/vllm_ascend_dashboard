import { useMemo, useState } from 'react'
import { Button, Card, Empty, Input, Space, Table, Tag, Typography, DatePicker } from 'antd'
import {
  CalendarOutlined,
  GithubOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import { useTestRuns } from '../hooks/useTestBoard'
import { TestRunItem } from '../services/testBoard'
import {
  formatDuration,
  renderConclusionTag,
  renderHardwareTag,
  renderStatusTag,
} from '../utils/ciRenderers'
import { formatTimezone, fromTimezoneNow } from '../utils/timezone'

const { Text } = Typography
const { RangePicker } = DatePicker

interface WorkflowTestExecutionTableProps {
  enabled: boolean
}

const RESULT_FILTERS = [
  { text: '成功', value: 'success' },
  { text: '失败', value: 'failure' },
  { text: '取消', value: 'cancelled' },
  { text: '已跳过', value: 'skipped' },
]

const STATUS_FILTERS = [
  { text: '已完成', value: 'completed' },
  { text: '进行中', value: 'in_progress' },
]

const toConclusion = (result: string | null) => {
  if (result === 'passed') return 'success'
  if (result === 'failed') return 'failure'
  if (result === 'skipped') return 'skipped'
  return result
}

const toStatus = (record: TestRunItem) => record.completed_at ? 'completed' : 'in_progress'

function WorkflowTestExecutionTable({ enabled }: WorkflowTestExecutionTableProps) {
  const [workflowFilter, setWorkflowFilter] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [resultFilter, setResultFilter] = useState<string[]>([])
  const [logSearch, setLogSearch] = useState('')
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const { data, isLoading, refetch } = useTestRuns(
    { days: 30, page: 1, per_page: 500 },
    enabled,
  )

  const workflowOptions = useMemo(() => (
    Array.from(new Set((data?.items || []).map((item) => item.workflow_name).filter(Boolean)))
      .map((workflowName) => ({ text: workflowName as string, value: workflowName as string }))
  ), [data?.items])

  const visibleRuns = useMemo(() => {
    const keyword = logSearch.trim().toLowerCase()
    return (data?.items || []).filter((item) => {
      if (workflowFilter.length > 0 && !workflowFilter.includes(item.workflow_name || '')) return false
      if (statusFilter.length > 0 && !statusFilter.includes(toStatus(item))) return false
      const conclusion = toConclusion(item.result)
      if (resultFilter.length > 0 && !resultFilter.includes(conclusion || '')) return false
      if (dateRange && item.started_at) {
        const startedAt = dayjs(formatTimezone(item.started_at, 'YYYY-MM-DD'))
        const [start, end] = dateRange
        if (start && startedAt.isBefore(start.startOf('day'))) return false
        if (end && startedAt.isAfter(end.endOf('day'))) return false
      } else if (dateRange && !item.started_at) {
        return false
      }
      if (!keyword) return true
      return [
        item.test_name,
        item.test_suite,
        item.job_name,
        item.failure_category,
        item.failure_message,
      ].some((value) => value?.toLowerCase().includes(keyword))
    })
  }, [data?.items, dateRange, logSearch, resultFilter, statusFilter, workflowFilter])

  const columns = [
    {
      title: '日期',
      key: 'run_date',
      width: 110,
      filterDropdown: () => (
        <div style={{ padding: 8 }} onClick={(event) => event.stopPropagation()}>
          <RangePicker
            value={dateRange as any}
            onChange={(dates) => setDateRange(dates as [Dayjs | null, Dayjs | null] | null)}
            allowClear
            format="YYYY-MM-DD"
            style={{ width: 260 }}
            placeholder={['开始日期', '结束日期']}
          />
        </div>
      ),
      filterIcon: () => <CalendarOutlined style={dateRange ? { color: '#1677ff' } : undefined} />,
      filtered: Boolean(dateRange),
      render: (_: unknown, record: TestRunItem) => record.started_at
        ? formatTimezone(record.started_at, 'YYYY-MM-DD')
        : '-',
    },
    {
      title: 'Workflow',
      dataIndex: 'workflow_name',
      key: 'workflow_name',
      width: 200,
      ellipsis: true,
      filters: workflowOptions,
      filteredValue: workflowFilter,
      onFilter: (value: boolean | React.Key, record: TestRunItem) => record.workflow_name === value,
      render: (text: string | null, record: TestRunItem) => (
        <Space size={4}>
          <span style={{ fontWeight: 500 }}>{text || '-'}</span>
          {record.ci_run_id && (
            <a
              href={`https://github.com/vllm-project/vllm-ascend/actions/runs/${record.ci_run_id}`}
              target="_blank"
              rel="noopener noreferrer"
              title="在 GitHub 上查看"
              onClick={(event) => event.stopPropagation()}
            >
              <GithubOutlined />
            </a>
          )}
        </Space>
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      sorter: (a: TestRunItem, b: TestRunItem) => {
        if (!a.started_at) return -1
        if (!b.started_at) return 1
        return new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
      },
      render: (startedAt: string | null) => startedAt ? (
        <Space direction="vertical" size={0}>
          <Text strong>{formatTimezone(startedAt, 'YYYY-MM-DD HH:mm:ss')}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{fromTimezoneNow(startedAt)}</Text>
        </Space>
      ) : '-',
    },
    {
      title: '硬件',
      dataIndex: 'test_hardware',
      key: 'test_hardware',
      width: 100,
      filters: Array.from(new Set((data?.items || []).map((item) => item.test_hardware).filter(Boolean)))
        .map((hardware) => ({ text: hardware as string, value: hardware as string })),
      onFilter: (value: boolean | React.Key, record: TestRunItem) => record.test_hardware === value,
      render: renderHardwareTag,
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      filters: STATUS_FILTERS,
      filteredValue: statusFilter,
      onFilter: (value: boolean | React.Key, record: TestRunItem) => toStatus(record) === value,
      render: (_: unknown, record: TestRunItem) => renderStatusTag(toStatus(record)),
    },
    {
      title: '结果',
      dataIndex: 'result',
      key: 'result',
      width: 100,
      filters: RESULT_FILTERS,
      filteredValue: resultFilter,
      onFilter: (value: boolean | React.Key, record: TestRunItem) => toConclusion(record.result) === value,
      render: (result: string | null) => renderConclusionTag(toConclusion(result)),
    },
    {
      title: '时长',
      dataIndex: 'duration_seconds',
      key: 'duration_seconds',
      width: 90,
      render: formatDuration,
    },
  ]

  const renderExpanded = (record: TestRunItem) => (
    <div style={{ padding: '12px 24px', background: '#fafafa' }}>
      <Space wrap size={[24, 8]}>
        <Text><Text strong>测试用例：</Text>{record.test_name || '-'}</Text>
        <Text><Text strong>测试套件：</Text>{record.test_suite || '-'}</Text>
        <Text><Text strong>Job：</Text>{record.job_name || '-'}</Text>
      </Space>
      <div style={{ marginTop: 8 }}>
        <Text strong>日志：</Text>{' '}
        <Text type={record.result === 'failed' ? 'danger' : 'secondary'}>
          {record.failure_message || record.failure_category || '无'}
        </Text>
      </div>
    </div>
  )

  const resetFilters = () => {
    setWorkflowFilter([])
    setStatusFilter([])
    setResultFilter([])
    setLogSearch('')
    setDateRange(null)
  }

  const hasFilters = Boolean(
    workflowFilter.length || statusFilter.length || resultFilter.length || logSearch || dateRange,
  )

  return (
    <Card
      title="运行记录"
      extra={(
        <Space>
          <RangePicker
            value={dateRange as any}
            onChange={(dates) => setDateRange(dates as [Dayjs | null, Dayjs | null] | null)}
            allowClear
            format="YYYY-MM-DD"
            placeholder={['开始日期', '结束日期']}
          />
          <Input.Search
            allowClear
            value={logSearch}
            onChange={(event) => setLogSearch(event.target.value)}
            placeholder="搜索用例、Job 或日志"
            style={{ width: 240 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isLoading}>刷新</Button>
          <Button onClick={resetFilters} disabled={!hasFilters}>重置筛选</Button>
        </Space>
      )}
    >
      <Table
        columns={columns}
        dataSource={visibleRuns}
        loading={isLoading}
        rowKey="id"
        pagination={{ pageSize: 20, showSizeChanger: false, showTotal: (total) => `共 ${total} 条` }}
        scroll={{ x: 1000 }}
        expandable={{ expandedRowRender: renderExpanded, expandRowByClick: true }}
        locale={{ emptyText: <Empty description="暂无运行记录" /> }}
        onChange={(_, filters) => {
          setWorkflowFilter((filters.workflow_name as string[] | null) || [])
          setStatusFilter((filters.status as string[] | null) || [])
          setResultFilter((filters.result as string[] | null) || [])
        }}
      />
    </Card>
  )
}

export default WorkflowTestExecutionTable
