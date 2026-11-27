export type WorkflowInputValue = string | number | boolean | null

export interface WorkflowInputDefinition {
  name: string
  type: string
  description: string
  required: boolean
  options: string[]
  default?: WorkflowInputValue
}
