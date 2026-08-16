import { useParams, useNavigate } from 'react-router-dom'
import { Card, Table, Tag, Button, Space, Typography, Descriptions, Divider, Alert, Tooltip, Switch, message } from 'antd'
import { useState } from 'react'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ArrowLeftOutlined,
  GithubOutlined,
  UserOutlined,
  EyeOutlined,
  FileSearchOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import { useJobsByRun, useRuns, useTestResultsByRun } from '../hooks/useCI'
import { useJobOwners } from '../hooks/useJobOwners'
import { useFailureAnalysisList, useAnalyzeFailedJob } from '../hooks/useFailureAnalysis'
import { useCurrentUser } from '../hooks/useCurrentUser'
import { PROBLEM_CATEGORY_MAP, ANALYSIS_STATUS_MAP } from '../services/failureAnalysis'
import { FailureAnalysisDetailModal } from '../components/FailureAnalysisDetailModal'
import dayjs from 'dayjs'
import duration from 'dayjs/plugin/duration'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import { formatTimezone, fromTimezoneNow } from '../utils/timezone'
import { renderStatusTag, renderConclusionTag, formatDuration, renderHardwareTag } from '../utils/ciRenderers'
import { CIRunTestResult } from '../services/ci'

dayjs.extend(duration)
dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const { Title, Text } = Typography

function WorkflowDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const runIdNum = runId ? parseInt(runId) : null

  const [conclusionFilter, setConclusionFilter] = useState<string[]>([])
  const [showSkipped, setShowSkipped] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [selectedAnalysis, setSelectedAnalysis] = useState<any>(null)

  const { data: jobs, isLoading: jobsLoading, refetch: refetchJobs } = useJobsByRun(runIdNum)
  const { data: testResults, isLoading: testResultsLoading, refetch: refetchTestResults } = useTestResultsByRun(runIdNum)
  const { data: runs, refetch: refetchRuns } = useRuns({ limit: 100 })
  const { data: jobOwners } = useJobOwners()
  const { data: analysisData } = useFailureAnalysisList({ days_back: 30 })
  const analyzeMutation = useAnalyzeFailedJob()
  const { data: currentUser } = useCurrentUser()
  const isAdmin = currentUser?.role === 'admin' || currentUser?.role === 'super_admin'

  const currentRun = runs?.find(r => r.run_id === runIdNum)

  const ownerMap = new Map<string, { owner: string; display_name?: string | null }>()
  jobOwners?.forEach(owner => {
    const key = `${owner.workflow_name}-${owner.job_name}`
    ownerMap.set(key, { owner: owner.owner, display_name: owner.display_name })
  })

  const analysisMap = new Map<number, any>()
  if (analysisData?.items) {
    for (const item of analysisData.items) {
      analysisMap.set(item.job_id, item)
    }
  }

  const handleRefresh = async () => {
    await Promise.all([refetchJobs(), refetchTestResults(), refetchRuns()])
    message.success('数据已刷新')
  }

  const handleViewAnalysis = (jobId: number) => {
    const analysis = analysisMap.get(jobId)
    setSelectedJobId(jobId)
    setSelectedAnalysis(analysis || null)
    setModalOpen(true)
  }

  const handleQuickAnalyze = (jobId: number) => {
    analyzeMutation.mutate(
      { jobId, force: true },
      {
        onSuccess: (data) => {
          message.success('分析已开始，请稍候...')
          // 自动打开弹窗，展示分析进度
          setSelectedJobId(jobId)
          setSelectedAnalysis(data)
          setModalOpen(true)
        },
        onError: (error: any) => {
          const detail = error?.response?.data?.detail || error?.message || '分析启动失败'
          message.error(detail)
        },
      }
    )
  }

  const columns = [
    {
      title: 'Job 名称',
      dataIndex: 'job_name',
      key: 'job_name',
      width: 250,
      ellipsis: true,
      render: (text: string, record: any) => {
        const ownerKey = `${record.workflow_name}-${record.job_name}`
        const ownerInfo = ownerMap.get(ownerKey)
        return (
          <Tooltip
            title={
              <div>
                <div><strong>Job:</strong> {text}</div>
                {ownerInfo?.display_name && <div><strong>显示名:</strong> {ownerInfo.display_name}</div>}
                {record.runner_name && <div><strong>Runner:</strong> {record.runner_name}</div>}
              </div>
            }
            placement="topLeft"
          >
            <div style={{ maxWidth: 230 }}>
              <Space direction="vertical" size={0}>
                <Text strong ellipsis>{text}</Text>
                {ownerInfo?.display_name && (
                  <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                    {ownerInfo.display_name}
                  </Text>
                )}
                {record.runner_name && (
                  <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                    Runner: {record.runner_name}
                  </Text>
                )}
              </Space>
            </div>
          </Tooltip>
        )
      },
    },
    {
      title: '硬件',
      dataIndex: 'hardware',
      key: 'hardware',
      render: renderHardwareTag,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: renderStatusTag,
    },
    {
      title: '结果',
      dataIndex: 'conclusion',
      key: 'conclusion',
      filters: [
        { text: '成功', value: 'success' },
        { text: '失败', value: 'failure' },
        { text: '取消', value: 'cancelled' },
        { text: '已跳过', value: 'skipped' },
        { text: '进行中', value: 'in_progress' },
        { text: '等待中', value: 'queued' },
        { text: '其他', value: 'other' },
      ],
      filteredValue: conclusionFilter,
      onFilter: (value: any, record: any) => {
        if (value === 'other') {
          return !['success', 'failure', 'cancelled', 'skipped', 'in_progress', 'queued'].includes(record.conclusion)
        }
        return record.conclusion === value
      },
      render: renderConclusionTag,
    },
    {
      title: '时长',
      dataIndex: 'duration_seconds',
      key: 'duration_seconds',
      render: formatDuration,
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (startedAt: string | null) => {
        if (!startedAt) return '-'
        return (
          <Space direction="vertical" size={0}>
            <Text>{formatTimezone(startedAt)}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {fromTimezoneNow(startedAt)}
            </Text>
          </Space>
        )
      },
    },
    {
      title: 'Steps',
      key: 'steps',
      render: (_: any, record: any) => {
        if (!record.steps_summary || record.steps_summary.length === 0) return '-'
        const successCount = record.steps_summary.filter((s: any) => s.conclusion === 'success').length
        const failureCount = record.steps_summary.filter((s: any) => s.conclusion === 'failure').length
        const skippedCount = record.steps_summary.filter((s: any) => s.conclusion === 'skipped').length

        return (
          <Space size="small">
            {successCount > 0 && (
              <Tag color="success" icon={<CheckCircleOutlined />}>{successCount}</Tag>
            )}
            {failureCount > 0 && (
              <Tag color="error" icon={<CloseCircleOutlined />}>{failureCount}</Tag>
            )}
            {skippedCount > 0 && (
              <Tag color="default">{skippedCount}</Tag>
            )}
          </Space>
        )
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: any, record: any) => {
        const isFailed = record.conclusion === 'failure' || record.conclusion === 'cancelled'
        return (
          <Space>
            <Button type="link" icon={<EyeOutlined />} onClick={() => navigate(`/ci/jobs/${record.job_id}`)} style={{ padding: 0 }}>
              详情
            </Button>
            {isFailed && (
              analysisMap.get(record.job_id) ? (
                <Button type="link" icon={<FileSearchOutlined />} onClick={() => handleViewAnalysis(record.job_id)} style={{ padding: 0 }}>
                  分析报告
                </Button>
              ) : (
                <Button
                  type="link"
                  icon={<RobotOutlined />}
                  loading={analyzeMutation.isPending && analyzeMutation.variables?.jobId === record.job_id}
                  onClick={() => handleQuickAnalyze(record.job_id)}
                  style={{ padding: 0 }}
                  disabled={!isAdmin}
                >
                  分析
                </Button>
              )
            )}
          </Space>
        )
      },
    },
    {
      title: '问题分类',
      key: 'problem_category',
      width: 100,
      render: (_: any, record: any) => {
        const analysis = analysisMap.get(record.job_id)
        if (!analysis || !analysis.problem_category) return '-'
        const catInfo = PROBLEM_CATEGORY_MAP[analysis.problem_category] || { color: '#64748d', label: analysis.problem_category }
        return <Tag color={catInfo.color}>{catInfo.label}</Tag>
      },
    },
    {
      title: '根因摘要',
      key: 'root_cause_summary',
      width: 180,
      ellipsis: true,
      render: (_: any, record: any) => {
        const analysis = analysisMap.get(record.job_id)
        if (!analysis?.root_cause_summary) return '-'
        return (
          <Tooltip title={analysis.root_cause_summary}>
            <Text ellipsis style={{ maxWidth: 160 }}>{analysis.root_cause_summary}</Text>
          </Tooltip>
        )
      },
    },
    {
      title: '改进建议',
      key: 'improvement_measures_summary',
      width: 180,
      ellipsis: true,
      render: (_: any, record: any) => {
        const analysis = analysisMap.get(record.job_id)
        if (!analysis?.improvement_measures_summary) return '-'
        return (
          <Tooltip title={analysis.improvement_measures_summary}>
            <Text ellipsis style={{ maxWidth: 160 }}>{analysis.improvement_measures_summary}</Text>
          </Tooltip>
        )
      },
    },
    {
      title: '分析状态',
      key: 'analysis_status',
      width: 100,
      render: (_: any, record: any) => {
        const analysis = analysisMap.get(record.job_id)
        if (!analysis) {
          if (record.conclusion === 'failure' || record.conclusion === 'cancelled') {
            return <Tag color="#64748d">未分析</Tag>
          }
          return '-'
        }
        const statusInfo = ANALYSIS_STATUS_MAP[analysis.analysis_status] || { color: '#64748d', label: analysis.analysis_status }
        return <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
      },
    },
    {
      title: '责任人',
      key: 'owner',
      render: (_: any, record: any) => {
        const ownerKey = `${record.workflow_name}-${record.job_name}`
        const ownerInfo = ownerMap.get(ownerKey)
        if (!ownerInfo) return '-'
        return (
          <Space>
            <UserOutlined />
            <Text>{ownerInfo.owner}</Text>
          </Space>
        )
      },
    },
  ]

  const testStats = {
    total: testResults?.length || 0,
    success: testResults?.filter(result => result.result === 'passed').length || 0,
    failure: testResults?.filter(result => result.result === 'failed').length || 0,
    unprocessed: testResults?.filter(result => result.result === 'failed' && result.processing_status === '未处理').length || 0,
  }

  const testResultColumns = [
    {
      title: '测试日期',
      key: 'test_date',
      width: 110,
      render: (_: unknown, record: CIRunTestResult) => record.started_at ? formatTimezone(record.started_at, 'YYYY-MM-DD') : '-',
    },
    {
      title: 'Workflow',
      dataIndex: 'workflow_name',
      key: 'workflow_name',
      width: 150,
      ellipsis: true,
    },
    {
      title: '测试用例',
      key: 'test_case',
      width: 260,
      ellipsis: true,
      render: (_: unknown, record: CIRunTestResult) => (
        <Tooltip title={`${record.test_suite} / ${record.test_name}`}>
          <Space direction="vertical" size={0}>
            <Text strong ellipsis>{record.display_name || record.test_name}</Text>
            <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
              {record.test_suite} · {record.test_type}
            </Text>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: 'Job',
      dataIndex: 'job_name',
      key: 'job_name',
      width: 220,
      ellipsis: true,
    },
    {
      title: '硬件',
      dataIndex: 'hardware',
      key: 'hardware',
      width: 80,
      render: renderHardwareTag,
    },
    {
      title: '负责人',
      dataIndex: 'owner',
      key: 'owner',
      width: 100,
      render: (owner: string | null) => owner ? <Space size={4}><UserOutlined /><Text>{owner}</Text></Space> : '-',
    },
    {
      title: '模型 / FO',
      key: 'model',
      width: 180,
      ellipsis: true,
      render: (_: unknown, record: CIRunTestResult) => record.model_fo || record.test_model || '-',
    },
    {
      title: '结果',
      dataIndex: 'conclusion',
      key: 'conclusion',
      width: 90,
      render: renderConclusionTag,
    },
    {
      title: '处理状态',
      dataIndex: 'processing_status',
      key: 'processing_status',
      width: 100,
      render: (status: string | null, record: CIRunTestResult) => status
        ? <Tag color={record.result === 'failed' ? 'warning' : 'success'}>{status}</Tag>
        : '-',
    },
    {
      title: '问题分类',
      dataIndex: 'problem_category',
      key: 'problem_category',
      width: 110,
      render: (category: string | null) => category || '-',
    },
    {
      title: '耗时',
      dataIndex: 'duration_seconds',
      key: 'duration_seconds',
      width: 90,
      render: formatDuration,
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 170,
      render: (startedAt: string | null) => startedAt ? formatTimezone(startedAt, 'MM-DD HH:mm:ss') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, record: CIRunTestResult) => record.github_job_url ? (
        <a href={record.github_job_url} target="_blank" rel="noopener noreferrer">
          <Button type="link" size="small" icon={<GithubOutlined />}>GitHub</Button>
        </a>
      ) : '-',
    },
  ]

  const stats = {
    total: jobs?.length || 0,
    executed: jobs?.filter(j => j.conclusion && j.conclusion !== 'skipped').length || 0,
    skipped: jobs?.filter(j => j.conclusion === 'skipped').length || 0,
    success: jobs?.filter(j => j.conclusion === 'success').length || 0,
    failure: jobs?.filter(j => j.conclusion === 'failure').length || 0,
    inProgress: jobs?.filter(j => j.status === 'in_progress').length || 0,
    cancelled: jobs?.filter(j => j.conclusion === 'cancelled').length || 0,
  }

  const visibleJobs = showSkipped
    ? jobs || []
    : (jobs || []).filter(job => job.conclusion !== 'skipped')

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/ci')}>
          返回 CI 看板
        </Button>
        {currentRun?.github_html_url && (
          <Button
            icon={<GithubOutlined />}
            href={currentRun.github_html_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            在 GitHub 上查看
          </Button>
        )}
      </Space>

      <Title level={2} style={{ marginBottom: 24 }}>
        Workflow 运行详情 {runIdNum ? `(#${runIdNum})` : ''}
      </Title>

      {!currentRun && !jobsLoading && (
        <Alert
          message="未找到 Workflow 运行记录"
          description={`数据库中找不到 run_id: ${runIdNum} 的记录，请确认 ID 是否正确，或先同步数据。`}
          type="warning"
          showIcon
          style={{ marginBottom: 24 }}
          action={
            <Button size="small" onClick={() => navigate('/ci')}>
              返回 CI 看板
            </Button>
          }
        />
      )}

      {currentRun && jobs && jobs.length === 0 && !jobsLoading && (
        <Alert
          message="暂无 Jobs 数据"
          description="该 Workflow 运行记录没有关联的 Jobs，可能是 GitHub API 未返回数据或该运行已被取消。"
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      {jobs && stats.skipped > 0 && (
        <Alert
          message={`此 Run 共 ${stats.total} 个 Jobs，实际执行 ${stats.executed} 个，已跳过 ${stats.skipped} 个`}
          description="这里展示的是 GitHub Actions 的 Job，不等同于测试用例数量；测试用例数需要从测试报告或构建产物中解析。列表默认隐藏已跳过的 Job。"
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      {currentRun && (
        <Card style={{ marginBottom: 24 }}>
          <Descriptions column={4} bordered>
            <Descriptions.Item label="Workflow">{currentRun.workflow_name}</Descriptions.Item>
            <Descriptions.Item label="Run ID">
              <Space size={4}>
                #{currentRun.run_id}
                {currentRun.github_html_url && (
                  <a
                    href={currentRun.github_html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="在 GitHub 上查看"
                  >
                    <GithubOutlined />
                  </a>
                )}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="Run Number">#{currentRun.run_number || '-'}</Descriptions.Item>
            <Descriptions.Item label="事件类型">{currentRun.event || '-'}</Descriptions.Item>
            <Descriptions.Item label="分支">{currentRun.branch || '-'}</Descriptions.Item>
            <Descriptions.Item label="Commit SHA">
              {currentRun.head_sha ? (
                <Text code style={{ fontSize: 12 }}>{currentRun.head_sha.substring(0, 7)}</Text>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="硬件">
              {currentRun.hardware ? (
                <Tag color={currentRun.hardware === 'A2' ? 'green' : 'purple'}>
                  {currentRun.hardware}
                </Tag>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {renderStatusTag(currentRun.status)}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Card title="测试结果概览（每日失败追踪口径）" style={{ marginBottom: 24 }}>
        <Space size="large" style={{ justifyContent: 'space-around', width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold' }}>{testStats.total}</div>
            <div style={{ color: '#999' }}>测试记录</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#52c41a' }}>{testStats.success}</div>
            <div style={{ color: '#999' }}>通过</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#ff4d4f' }}>{testStats.failure}</div>
            <div style={{ color: '#999' }}>失败</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#faad14' }}>{testStats.unprocessed}</div>
            <div style={{ color: '#999' }}>待处理</div>
          </div>
        </Space>
      </Card>

      {currentRun && testResults && testResults.length === 0 && !testResultsLoading && (
        <Alert
          message="尚未解析到测试结果"
          description="该 Run 可能只包含工作流编排或基础设施 Job，或者测试报告尚未被收集。下面的原始 Jobs 仅用于诊断，不计入测试用例统计。"
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      <Card title="测试结果（按测试记录展示）" style={{ marginBottom: 24 }}>
        <Table
          columns={testResultColumns}
          dataSource={testResults || []}
          loading={testResultsLoading}
          rowKey="id"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 1700 }}
        />
      </Card>

      <Card style={{ marginBottom: 24 }}>
        <Space size="large" style={{ justifyContent: 'space-around', width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold' }}>{stats.total}</div>
            <div style={{ color: '#999' }}>总 Jobs（含跳过）</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1890ff' }}>{stats.executed}</div>
            <div style={{ color: '#999' }}>实际执行</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#8c8c8c' }}>{stats.skipped}</div>
            <div style={{ color: '#999' }}>已跳过</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#52c41a' }}>{stats.success}</div>
            <div style={{ color: '#999' }}>成功</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#ff4d4f' }}>{stats.failure}</div>
            <div style={{ color: '#999' }}>失败</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1890ff' }}>{stats.inProgress}</div>
            <div style={{ color: '#999' }}>进行中</div>
          </div>
          <Divider type="vertical" style={{ height: 40 }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#faad14' }}>{stats.cancelled}</div>
            <div style={{ color: '#999' }}>已取消</div>
          </div>
        </Space>
      </Card>

      <Card
        title="Jobs 列表"
        extra={
          <Space>
            <Text type="secondary">显示已跳过 Jobs</Text>
            <Switch checked={showSkipped} onChange={setShowSkipped} />
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={visibleJobs}
          loading={jobsLoading}
          rowKey="job_id"
          pagination={{
            pageSize: 20,
            showSizeChanger: false,
          }}
          scroll={{ x: 'max-content' }}
          onChange={(_, filters) => {
            if (filters.conclusion) {
              const selected = filters.conclusion as string[]
              setConclusionFilter(selected)
              if (selected.includes('skipped')) {
                setShowSkipped(true)
              }
            } else {
              setConclusionFilter([])
            }
          }}
        />
      </Card>

      <FailureAnalysisDetailModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        jobId={selectedJobId}
        existingAnalysis={selectedAnalysis}
      />
    </div>
  )
}

export default WorkflowDetail
