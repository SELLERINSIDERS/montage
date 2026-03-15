import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { isStale, getStageForPhase } from '../utils'

describe('isStale', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-11T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns true when heartbeat >30min old and status is active', () => {
    const heartbeat = new Date('2026-03-11T11:00:00Z').toISOString() // 60min old
    expect(isStale(heartbeat, 'active')).toBe(true)
  })

  it('returns false when heartbeat is recent', () => {
    const heartbeat = new Date('2026-03-11T11:45:00Z').toISOString() // 15min old
    expect(isStale(heartbeat, 'active')).toBe(false)
  })

  it('returns false when status is completed even if heartbeat is old', () => {
    const heartbeat = new Date('2026-03-11T10:00:00Z').toISOString() // 2h old
    expect(isStale(heartbeat, 'completed')).toBe(false)
  })

  it('returns false when heartbeatAt is null', () => {
    expect(isStale(null, 'active')).toBe(false)
  })

  it('returns false when status is paused', () => {
    const heartbeat = new Date('2026-03-11T10:00:00Z').toISOString()
    expect(isStale(heartbeat, 'paused')).toBe(false)
  })

  it('returns false when currentPhase is complete even if heartbeat is old', () => {
    const heartbeat = new Date('2026-03-11T10:00:00Z').toISOString() // 2h old
    expect(isStale(heartbeat, 'active', 'complete')).toBe(false)
  })

  it('returns false when currentPhase is delivered', () => {
    const heartbeat = new Date('2026-03-11T10:00:00Z').toISOString()
    expect(isStale(heartbeat, 'active', 'delivered')).toBe(false)
  })

  it('returns true when currentPhase is mid-pipeline and heartbeat old', () => {
    const heartbeat = new Date('2026-03-11T11:00:00Z').toISOString() // 60min old
    expect(isStale(heartbeat, 'active', 'video_generation')).toBe(true)
  })

  it('returns true when currentPhase is undefined (backwards compatible)', () => {
    const heartbeat = new Date('2026-03-11T11:00:00Z').toISOString() // 60min old
    expect(isStale(heartbeat, 'active')).toBe(true)
  })
})

describe('getStageForPhase', () => {
  it('maps script to Script & Design', () => {
    expect(getStageForPhase('script')).toBe('Script & Design')
  })

  it('maps image_1k to Image Gen', () => {
    expect(getStageForPhase('image_1k')).toBe('Image Gen')
  })

  it('maps video_generation to Video Gen', () => {
    expect(getStageForPhase('video_generation')).toBe('Video Gen')
  })

  it('maps voiceover to Audio & Post', () => {
    expect(getStageForPhase('voiceover')).toBe('Audio & Post')
  })

  it('maps complete to Complete', () => {
    expect(getStageForPhase('complete')).toBe('Complete')
  })

  it('returns first stage for unknown phase', () => {
    expect(getStageForPhase('unknown_phase')).toBe('Script & Design')
  })
})
