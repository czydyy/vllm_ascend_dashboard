import { describe, expect, it } from 'vitest'

import type { CIStats } from '../services/ci'
import {
  buildDailyDurationOverview,
  buildDurationAxis,
  buildRunDurationPoints,
  formatPercentage,
  toBuildStatsSummary,
} from './ciBuildStats'

describe('toBuildStatsSummary', () => {
  it('maps success, failure and other counts from the API', () => {
    const stats: CIStats = {
      total_runs: 10,
      passed_runs: 6,
      failed_runs: 2,
      other_runs: 2,
      success_rate: 60,
      avg_duration_seconds: 149,
      last_7_days: null,
    }

    expect(toBuildStatsSummary(stats)).toEqual({
      totalRuns: 10,
      passedRuns: 6,
      failedRuns: 2,
      otherRuns: 2,
      passRate: 60,
      averageDurationMinutes: 2,
    })
  })

  it('uses stable zero values when data is absent', () => {
    expect(toBuildStatsSummary()).toEqual({
      totalRuns: 0,
      passedRuns: 0,
      failedRuns: 0,
      otherRuns: 0,
      passRate: 0,
      averageDurationMinutes: 0,
    })
  })
})

describe('formatPercentage', () => {
  it('rounds the API percentage for compact display', () => {
    expect(formatPercentage(87.51)).toBe('88%')
    expect(formatPercentage(0)).toBe('0%')
  })
})

describe('build duration chart data', () => {
  it('orders completed runs and maps failure colours without inventing durations', () => {
    const points = buildRunDurationPoints([
      { run_id: 2, conclusion: 'failure', started_at: '2026-09-02T01:00:00Z', completed_at: '2026-09-02T03:00:00Z', duration_seconds: 7200 },
      { run_id: 3, conclusion: 'success', started_at: '2026-09-03T01:00:00Z', completed_at: null, duration_seconds: null },
      { run_id: 1, conclusion: 'success', started_at: '2026-09-01T01:00:00Z', completed_at: '2026-09-01T02:00:00Z', duration_seconds: 3600 },
    ])

    expect(points.map((point) => ({ id: point.id, duration: point.durationMinutes, failed: point.failed }))).toEqual([
      { id: 1, duration: 60, failed: false },
      { id: 2, duration: 120, failed: true },
    ])
  })

  it('groups workflows by Beijing start date instead of completion date', () => {
    const points = buildRunDurationPoints([
      {
        run_id: 4,
        conclusion: 'success',
        started_at: '2026-09-02T22:54:43Z',
        completed_at: '2026-09-04T01:00:00Z',
        duration_seconds: 7200,
      },
    ])

    expect(points[0]).toMatchObject({
      dateKey: '2026-09-03',
      dateLabel: '9月3日',
      timestamp: '9月3日',
      tooltipLabel: '2026/9/3 06:54:43',
    })
  })

  it('calculates daily p50, p90 and peak values for Overview mode', () => {
    const points = buildRunDurationPoints([
      { run_id: 1, conclusion: 'success', started_at: '2026-09-01T01:00:00Z', completed_at: '2026-09-01T02:00:00Z', duration_seconds: 60 },
      { run_id: 2, conclusion: 'failure', started_at: '2026-09-01T02:00:00Z', completed_at: '2026-09-01T03:00:00Z', duration_seconds: 180 },
    ])

    expect(buildDailyDurationOverview(points)).toMatchObject([
      {
        p50: 1,
        p90: 3,
        p50ToP90: 2,
        peak: 3,
        passed: 1,
        failed: 1,
        passRate: 50,
      },
    ])
  })
})

describe('buildDurationAxis', () => {
  it('uses readable whole-hour ticks close to the displayed maximum', () => {
    expect(buildDurationAxis(8 * 60)).toEqual({
      maxMinutes: 8 * 60,
      ticks: [0, 120, 240, 360, 480],
    })
  })

  it('keeps short build durations visible with a one-hour minimum', () => {
    expect(buildDurationAxis(20)).toEqual({ maxMinutes: 60, ticks: [0, 60] })
  })
})
