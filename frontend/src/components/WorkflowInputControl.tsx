import { Input, InputNumber, Select, Switch } from 'antd'
import type { WorkflowInputDefinition } from '../types/workflowInputs'

export function renderWorkflowInput(input: WorkflowInputDefinition) {
  switch (input.type) {
    case 'boolean':
      return <Switch />
    case 'choice':
    case 'environment':
      return (
        <Select
          showSearch
          disabled={input.type === 'environment' && input.options.length === 0}
          placeholder={input.type === 'environment' ? '选择 GitHub 环境' : undefined}
          options={input.options.map((option) => ({ value: option, label: option }))}
        />
      )
    case 'number':
      return <InputNumber style={{ width: '100%' }} />
    case 'string':
    default:
      return <Input />
  }
}
