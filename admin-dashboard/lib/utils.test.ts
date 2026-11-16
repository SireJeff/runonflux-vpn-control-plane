import { describe, it, expect } from 'vitest'
import { formatSnapshotTrafficGb } from './utils'

describe('formatSnapshotTrafficGb', () => {
  it('renders GB from the backend traffic_gb key', () => {
    expect(formatSnapshotTrafficGb({ traffic_gb: 50 })).toBe('50.0 GB')
  })

  it('formats to one decimal place', () => {
    expect(formatSnapshotTrafficGb({ traffic_gb: 12.34 })).toBe('12.3 GB')
  })

  it('returns a dash when traffic_gb is absent (e.g. legacy traffic_limit_gb key)', () => {
    expect(formatSnapshotTrafficGb({ traffic_limit_gb: 50 } as never)).toBe('-')
  })

  it('returns a dash for null/undefined snapshot', () => {
    expect(formatSnapshotTrafficGb(null)).toBe('-')
    expect(formatSnapshotTrafficGb(undefined)).toBe('-')
  })
})
