import dayjs from 'dayjs'

export type OccupancyView = 'pool' | 'project'
export type OccupancyRange = '1h' | '24h' | '7d' | '30d' | 'custom'

export interface OccupancyDimension {
  id: string
  name: string
  capacity?: number
  color: string
}

export interface OccupancyPoint {
  time: string
  values: Record<string, number>
}

export interface OccupancyTask {
  id: string
  project: string
  pool: string
  workflow: string
  cards: number
  node: string
  npuList: string
  status: 'active' | 'expired'
  startedAt: string
  endsAt: string
}

export const mockPools: OccupancyDimension[] = [
  { id: 'sglang', name: 'SGLang 910C', capacity: 224, color: '#1677ff' },
  { id: 'vllm', name: 'vLLM 910C', capacity: 144, color: '#13c2c2' },
  { id: 'pytorch', name: 'PyTorch 910C', capacity: 112, color: '#722ed1' },
  { id: 'verl', name: 'VeRL 910C', capacity: 144, color: '#fa8c16' },
  { id: 'north', name: '华北 A3', capacity: 224, color: '#eb2f96' },
]

export const mockProjects: OccupancyDimension[] = [
  { id: 'vllm-ascend', name: 'vllm-project/vllm-ascend', color: '#1677ff' },
  { id: 'sglang', name: 'sgl-project/sglang', color: '#13c2c2' },
  { id: 'pytorch', name: 'Ascend/pytorch', color: '#722ed1' },
  { id: 'triton', name: 'triton-lang/triton-ascend', color: '#fa8c16' },
]

const rangeConfig: Record<Exclude<OccupancyRange, 'custom'>, { amount: number; unit: dayjs.ManipulateType; stepMinutes: number }> = {
  '1h': { amount: 1, unit: 'hour', stepMinutes: 10 },
  '24h': { amount: 24, unit: 'hour', stepMinutes: 30 },
  '7d': { amount: 7, unit: 'day', stepMinutes: 120 },
  '30d': { amount: 30, unit: 'day', stepMinutes: 720 },
}

const poolWeights: Record<string, number> = { sglang: 1, vllm: 0.72, pytorch: 0.48, verl: 0.61, north: 0.78 }
const projectWeights: Record<string, number> = { 'vllm-ascend': 0.85, sglang: 1, pytorch: 0.51, triton: 0.36 }

function valueAt(index: number, dimensionIndex: number, weight: number) {
  const wave = 0.52 + Math.sin(index / 5 + dimensionIndex * 1.7) * 0.18 + Math.cos(index / 13 + dimensionIndex) * 0.1
  const pulse = index % 17 === dimensionIndex * 3 ? 0.12 : 0
  return Math.max(4, Math.round((wave + pulse) * 170 * weight / 2) * 2)
}

export function getMockOccupancyTimeline(view: OccupancyView, range: OccupancyRange, customRange?: [string, string] | null): OccupancyPoint[] {
  const configured = range === 'custom' ? undefined : rangeConfig[range]
  const start = customRange ? dayjs(customRange[0]).startOf('minute') : dayjs().startOf('minute').subtract(configured!.amount, configured!.unit)
  const end = customRange ? dayjs(customRange[1]).startOf('minute') : dayjs().startOf('minute')
  const durationMinutes = Math.max(end.diff(start, 'minute'), 1)
  const stepMinutes = configured?.stepMinutes ?? (durationMinutes <= 24 * 60 ? 30 : durationMinutes <= 7 * 24 * 60 ? 120 : 720)
  const dimensions = view === 'pool' ? mockPools : mockProjects
  const points: OccupancyPoint[] = []
  let cursor = start
  let index = 0
  while (cursor.isBefore(end) || cursor.isSame(end)) {
    const values = Object.fromEntries(dimensions.map((dimension, dimensionIndex) => [
      dimension.id,
      valueAt(index, dimensionIndex, (view === 'pool' ? poolWeights : projectWeights)[dimension.id]),
    ]))
    points.push({ time: cursor.toISOString(), values })
    cursor = cursor.add(stepMinutes, 'minute')
    index += 1
  }
  return points
}

export function getMockTasks(time: string): OccupancyTask[] {
  const at = dayjs(time)
  return [
    {
      id: 'demo-env-001', project: 'vllm-project/vllm-ascend', pool: 'vLLM 910C',
      workflow: 'nightly / run-selected-tests', cards: 8, node: '192.168.0.34', npuList: '0,1,2,3,4,5,6,7',
      status: 'active', startedAt: at.subtract(46, 'minute').format('YYYY-MM-DD HH:mm'), endsAt: '快照时刻',
    },
    {
      id: 'demo-env-002', project: 'sgl-project/sglang', pool: 'SGLang 910C',
      workflow: 'base-b-test-8-npu-a3 / run', cards: 16, node: '192.168.0.151', npuList: '0-15',
      status: 'active', startedAt: at.subtract(2, 'hour').format('YYYY-MM-DD HH:mm'), endsAt: '快照时刻',
    },
    {
      id: 'demo-env-003', project: 'Ascend/pytorch', pool: 'PyTorch 910C',
      workflow: 'integration-tests-ascend', cards: 4, node: '172.22.3.138', npuList: '12,13,14,15',
      status: 'expired', startedAt: at.subtract(74, 'minute').format('YYYY-MM-DD HH:mm'), endsAt: at.add(18, 'minute').format('YYYY-MM-DD HH:mm'),
    },
    {
      id: 'demo-env-004', project: 'triton-lang/triton-ascend', pool: '华北 A3',
      workflow: 'integration-tests / linux-aarch64-a3', cards: 4, node: '192.168.0.163', npuList: '8,9,10,11',
      status: 'active', startedAt: at.subtract(33, 'minute').format('YYYY-MM-DD HH:mm'), endsAt: '快照时刻',
    },
  ]
}

export function mockRawTask(task: OccupancyTask) {
  return {
    env_id: task.id,
    status: task.status,
    created_at: task.startedAt,
    expires_at: task.status === 'active' ? null : task.endsAt,
    resources: [{ type: 'npu', npu: task.cards, node_ip: task.node, npu_list: task.npuList }],
    annotations: { project: task.project, workflow: task.workflow },
    note: '演示数据：真实接入后由 pod-history-api 原始记录替换。',
  }
}
