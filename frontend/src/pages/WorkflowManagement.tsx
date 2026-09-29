import { useState } from 'react'
import { Card, Table, Button, Space, Tag, Switch, message, Modal, Form, Input, InputNumber, Select, Row, Col } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'

const { Option } = Select
const { TextArea } = Input

interface Workflow {
  id: number
  workflow_name: string
  workflow_file: string
  hardware: string
  description?: string
  enabled: boolean
  display_order: number
}

// 获取所有 workflows
const useWorkflows = () => {
  return useQuery({
    queryKey: ['workflows'],
    queryFn: async () => {
      const response = await api.get<Workflow[]>('/workflows')
      return response.data
    },
  })
}

// 创建 workflow
const useCreateWorkflow = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Workflow>) => api.post('/workflows', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      message.success('创建成功')
    },
    onError: () => {
      message.error('创建失败')
    },
  })
}

// 更新 workflow
const useUpdateWorkflow = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Workflow> }) =>
      api.put(`/workflows/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      message.success('更新成功')
    },
    onError: () => {
      message.error('更新失败')
    },
  })
}

// 删除 workflow
const useDeleteWorkflow = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/workflows/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      message.success('删除成功')
    },
    onError: () => {
      message.error('删除失败')
    },
  })
}

// 切换启用状态
const useToggleWorkflow = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post(`/workflows/${id}/toggle`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}

function WorkflowManagement() {
  const [modalVisible, setModalVisible] = useState(false)
  const [editingWorkflow, setEditingWorkflow] = useState<Workflow | null>(null)
  const [form] = Form.useForm()

  const { data: workflows, isLoading } = useWorkflows()
  const createMutation = useCreateWorkflow()
  const updateMutation = useUpdateWorkflow()
  const deleteMutation = useDeleteWorkflow()
  const toggleMutation = useToggleWorkflow()

  // 打开创建/编辑弹窗
  const handleOpenModal = (record?: Workflow) => {
    if (record) {
      setEditingWorkflow(record)
      form.setFieldsValue(record)
    } else {
      setEditingWorkflow(null)
      form.resetFields()
    }
    setModalVisible(true)
  }

  // 保存创建/编辑
  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      if (editingWorkflow) {
        await updateMutation.mutateAsync({ id: editingWorkflow.id, data: values })
      } else {
        await createMutation.mutateAsync(values)
      }
      setModalVisible(false)
    } catch (error) {
      console.error('Validation failed:', error)
    }
  }

  // 删除确认
  const handleDelete = (record: Workflow) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 workflow "${record.workflow_name}" 吗？`,
      onOk: async () => {
        await deleteMutation.mutateAsync(record.id)
      },
    })
  }

  // 切换启用状态
  const handleToggleEnabled = async (record: Workflow) => {
    await toggleMutation.mutateAsync(record.id)
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'workflow_name',
      key: 'workflow_name',
      render: (text: string) => <strong>{text}</strong>,
    },
    {
      title: '文件名',
      dataIndex: 'workflow_file',
      key: 'workflow_file',
      render: (text: string) => <code>{text}</code>,
    },
    {
      title: '硬件',
      dataIndex: 'hardware',
      key: 'hardware',
      render: (hardware: string) => (
        <Tag color={hardware === 'A2' ? 'green' : hardware === 'A3' ? 'purple' : 'orange'}>
          {hardware}
        </Tag>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '顺序',
      dataIndex: 'display_order',
      key: 'display_order',
      width: 80,
    },
    {
      title: '状态',
      key: 'enabled',
      width: 100,
      render: (_: any, record: Workflow) => (
        <Switch
          checked={record.enabled}
          onChange={() => handleToggleEnabled(record)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: any, record: Workflow) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleOpenModal(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card
        title="Workflow 配置管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => handleOpenModal()}>
            添加 Workflow
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={workflows || []}
          loading={isLoading}
          rowKey="id"
          pagination={false}
        />
      </Card>

      {/* 创建/编辑弹窗 */}
      <Modal
        title={editingWorkflow ? '编辑 Workflow' : '添加 Workflow'}
        open={modalVisible}
        onOk={handleSave}
        onCancel={() => setModalVisible(false)}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        width={600}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="workflow_name"
                label="显示名称"
                rules={[{ required: true, message: '请输入名称' }]}
              >
                <Input placeholder="如：Nightly-A2" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="hardware"
                label="硬件类型"
                rules={[{ required: true, message: '请选择硬件类型' }]}
              >
                <Select>
                  <Option value="A2">A2</Option>
                  <Option value="A3">A3</Option>
                  <Option value="A5">A5</Option>
                  <Option value="310P">310P</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="workflow_file"
            label="Workflow 文件名"
            rules={[{ required: true, message: '请输入文件名' }]}
          >
            <Input placeholder="如：schedule_nightly_test_a2.yaml" disabled={!!editingWorkflow} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="描述该 workflow 的用途" />
          </Form.Item>
          <Form.Item name="display_order" label="显示顺序" initialValue={0}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default WorkflowManagement
