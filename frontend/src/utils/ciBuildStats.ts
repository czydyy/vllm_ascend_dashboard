import type { CIStats } from '../services/ci'

export type CIBuildStatsSummary = {
  totalRuns: number
  passedRuns: number
  failedRuns: number
  otherRuns: number
  passRate: number
  averageDurationMinutes: number
}

/** Convert the API response into safe display values for the Builds cards. */
export function toBuildStatsSummary(stats?: CIStats | null): CIBuildStatsSummary {
  return {
    totalRuns: stats?.total_runs ?? 0,
    passedRuns: stats?.passed_runs ?? 0,
    failedRuns: stats?.failed_runs ?? 0,
    otherRuns: stats?.other_runs ?? 0,
    passRate: stats?.success_rate ?? 0,
    averageDurationMinutes: stats?.avg_duration_seconds == null
      ? 0
      : Math.round(stats.avg_duration_seconds / 60),
  }
}

export function formatPercentage(value: number): string {
  return `${Math.round(value)}%`
}

export type BuildRunDurationPoint = {
  id: number
  dateKey: string
  dateLabel: string
  timestamp: string
  tooltipLabel: string
  durationMinutes: number
  failed: boolean
}

export type BuildDailyDurationPoint = {
  dateKey: string
  dateLabel: string
  p50: number
  p90: number
  p50ToP90: number
  peak: number
  passed: number
  failed: number
  passRate: number
}

export function buildRunDurationPoints(runs: Array<{
  run_id: number
  conclusion: string | null
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
}>): BuildRunDurationPoint[] {
  return [...runs]
    .filter((run) => run.duration_seconds != null && (run.completed_at || run.started_at))
    .sort((left, right) => {
      const leftTime = left.completed_at || left.started_at as string
      const rightTime = right.completed_at || right.started_at as string
      return leftTime.localeCompare(rightTime)
    })
    .map((run) => {
      const rawTime = run.completed_at || run.started_at as string
      const date = new Date(rawTime)
      return {
        id: run.run_id,
        dateKey: rawTime.slice(0, 10),
        dateLabel: date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
        timestamp: date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
        tooltipLabel: date.toLocaleString('zh-CN'),
        durationMinutes: (run.duration_seconds as number) / 60,
        failed: run.conclusion === 'failure',
      }
    })
}

function percentile(sorted: number[], ratio: number): number {
  return sorted[Math.max(0, Math.ceil(sorted.length * ratio) - 1)] ?? 0
}

export function buildDailyDurationOverview(
  points: BuildRunDurationPoint[],
): BuildDailyDurationPoint[] {
  const groups = new Map<string, BuildRunDurationPoint[]>()
  for (const point of points) {
    groups.set(point.dateKey, [...(groups.get(point.dateKey) ?? []), point])
  }

  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([dateKey, day]) => {
    const durations = day.map((point) => point.durationMinutes).sort((a, b) => a - b)
    const p50 = percentile(durations, 0.5)
    const p90 = percentile(durations, 0.9)
    const passed = day.filter((point) => !point.failed).length
    const failed = day.filter((point) => point.failed).length
    return {
      dateKey,
      dateLabel: day[0].dateLabel,
      p50,
      p90,
      p50ToP90: p90 - p50,
      peak: durations[durations.length - 1] ?? 0,
      passed,
      failed,
      passRate: day.length > 0 ? passed / day.length * 100 : 0,
    }
  })
}

export function buildDurationAxis(maxDurationMinutes: number): {
  maxMinutes: number
  ticks: number[]
} {
  const maxHours = Math.max(1, Math.ceil(maxDurationMinutes / 60))
  const stepHours = Math.max(1, Math.ceil(maxHours / 6))
  const axisMaxHours = Math.ceil(maxHours / stepHours) * stepHours
  const ticks = Array.from(
    { length: axisMaxHours / stepHours + 1 },
    (_, index) => index * stepHours * 60,
  )
  return { maxMinutes: axisMaxHours * 60, ticks }
}
