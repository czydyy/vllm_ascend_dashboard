import { Button, Form, Space, Typography } from 'antd'
import { SyncOutlined } from '@ant-design/icons'
import { renderWorkflowInput } from '../../../components/WorkflowInputControl'
import type { DailyTriggerWorkflow } from '../../../types/dailyPipeline'

const labels: Record<string, string> = {
  update_est_times: '更新预估耗时',
}

export default function DailyWorkflowFields({ workflow, canEdit, onSync }: {
  workflow?: DailyTriggerWorkflow | null
  canEdit: boolean
  onSync: () => void
}) {
  return <section className="daily-trigger-workflow">
    <Space wrap className="daily-trigger-workflow-heading">
      <Typography.Text strong>Workflow 参数</Typography.Text>
      {canEdit && <Button type="link" size="small" icon={<SyncOutlined />} onClick={onSync}>同步 Workflow</Button>}
    </Space>
    {workflow ? workflow.inputs.map((field) => (
      <Form.Item key={field.name} name={['workflowInputs', field.name]} label={labels[field.name] ?? field.name}
        wrapperCol={{ flex: '0 1 320px' }} tooltip={field.description || undefined}
        valuePropName={field.type === 'boolean' ? 'checked' : 'value'} preserve={false}>
        {renderWorkflowInput(field)}
      </Form.Item>
    )) : <Typography.Text type="secondary">暂无已同步的参数</Typography.Text>}
  </section>
}
