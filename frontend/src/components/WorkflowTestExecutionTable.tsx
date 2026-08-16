import { useMemo, useState } from 'react'
import { Button, Card, Empty, Input, Space, Table, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useTestRuns } from '../hooks/useTestBoard'
import { TestRunItem } from '../services/testBoard'
import { formatDuration } from '../utils/ciRenderers'
import { formatTimezone } from '../utils/timezone'

const { Text } = Typography

interface WorkflowTestExecutionTableProps {
  enabled: boolean
}

const RESULT_FILTERS = [
  { text: '通过', value: 'passed' },
  { text: '失败', value: 'failed' },
  { text: '跳过', value: 'skipped' },
  { text: '未知', value: 'unknown' },
]

const renderTestResult = (result: string) => {
  const resultMap: Record<string, { color: string; label: string }> = {
    passed: { color: 'success', label: '通过' },
    failed: { color: 'error', label: '失败' },
    skipped: { color: 'default', label: '跳过' },
  }
  const config = resultMap[result] || { color: 'warning', label: result || '未知' }
  return <Tag color={config.color}>{config.label}</Tag>
}

function WorkflowTestExecutionTable({ enabled }: WorkflowTestExecutionTableProps) {
  const [workflowFilter, setWorkflowFilter] = useState<string[]>([])
  const [resultFilter, setResultFilter] = useState<string[]>([])
  const [logSearch, setLogSearch] = useState('')
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
      if (workflowFilter.length > 0 && !workflowFilter.includes(item.workflow_name || '')) {
        return false
      }
      if (resultFilter.length > 0 && !resultFilter.includes(item.result)) {
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
  }, [data?.items, logSearch, resultFilter, workflowFilter])

  const columns = [
    {
      title: 'Workflow',
      dataIndex: 'workflow_name',
      key: 'workflow_name',
      width: 160,
      filters: workflowOptions,
      filteredValue: workflowFilter,
      onFilter: (value: boolean | React.Key, record: TestRunItem) => record.workflow_name === value,
      render: (value: string | null) => value || '-',
    },
    {
      title: '测试用例',
      dataIndex: 'test_name',
      key: 'test_name',
      width: 280,
      ellipsis: true,
      render: (value: string | null, record: TestRunItem) => (
        <Space direction="vertical" size={0}>
          <Text ellipsis style={{ maxWidth: 260 }}>{value || '-'}</Text>
          {record.test_suite && <Text type="secondary" style={{ fontSize: 12 }}>{record.test_suite}</Text>}
        </Space>
      ),
    },
    {
      title: 'Job',
      dataIndex: 'job_name',
      key: 'job_name',
      width: 240,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '结果',
      dataIndex: 'result',
      key: 'result',
      width: 90,
      filters: RESULT_FILTERS,
      filteredValue: resultFilter,
      onFilter: (value: boolean | React.Key, record: TestRunItem) => record.result === value,
      render: renderTestResult,
    },
    {
      title: '日志',
      dataIndex: 'failure_message',
      key: 'failure_message',
      width: 300,
      ellipsis: true,
      render: (value: string | null, record: TestRunItem) => (
        <Text type={record.result === 'failed' ? 'danger' : 'secondary'} ellipsis>
          {value || record.failure_category || '-'}
        </Text>
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 170,
      render: (value: string | null) => value ? formatTimezone(value, 'YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '耗时',
      dataIndex: 'duration_seconds',
      key: 'duration_seconds',
      width: 90,
      render: formatDuration,
    },
  ]

  const resetFilters = () => {
    setWorkflowFilter([])
    setResultFilter([])
    setLogSearch('')
  }

  return (
    <Card
      title="运行记录"
      extra={(
        <Space>
          <Input.Search
            allowClear
            value={logSearch}
            onChange={(event) => setLogSearch(event.target.value)}
            placeholder="搜索用例、Job 或日志"
            style={{ width: 240 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isLoading}>
            刷新
          </Button>
          <Button onClick={resetFilters} disabled={!workflowFilter.length && !resultFilter.length && !logSearch}>
            重置筛选
          </Button>
        </Space>
      )}
    >
      <Table
        columns={columns}
        dataSource={visibleRuns}
        loading={isLoading}
        rowKey="id"
        pagination={{ pageSize: 20, showSizeChanger: false, showTotal: (total) => `共 ${total} 条` }}
        scroll={{ x: 1300 }}
        locale={{ emptyText: <Empty description="暂无用例执行数据" /> }}
        onChange={(_, filters) => {
          setWorkflowFilter((filters.workflow_name as string[] | null) || [])
          setResultFilter((filters.result as string[] | null) || [])
        }}
      />
    </Card>
  )
}

export default WorkflowTestExecutionTable
