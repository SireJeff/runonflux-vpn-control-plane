import { describe, it, expect } from 'vitest'
import { formatErrorDetail } from './client'

describe('formatErrorDetail', () => {
  it('passes a plain HTTPException string through', () => {
    expect(formatErrorDetail("Username 'x' already exists", 'fallback')).toBe(
      "Username 'x' already exists"
    )
  })

  it('turns a FastAPI 422 detail array into a readable string (React #31 guard)', () => {
    // This is the exact shape that crashed the page when rendered directly.
    const detail = [
      {
        type: 'string_pattern_mismatch',
        loc: ['body', 'username'],
        msg: 'String should match pattern',
        input: 'bad user',
        ctx: { pattern: '^[a-zA-Z0-9_]+$' },
        url: 'https://errors.pydantic.dev/2.5/v/string_pattern_mismatch',
      },
    ]
    const out = formatErrorDetail(detail, 'Validation error')
    expect(typeof out).toBe('string')
    expect(out).toBe('username: String should match pattern')
  })

  it('joins multiple validation errors', () => {
    const detail = [
      { loc: ['body', 'username'], msg: 'too short' },
      { loc: ['body', 'traffic_limit_gb'], msg: 'must be > 0' },
    ]
    expect(formatErrorDetail(detail, 'Validation error')).toBe(
      'username: too short; traffic_limit_gb: must be > 0'
    )
  })

  it('handles a single error object with a msg', () => {
    expect(formatErrorDetail({ msg: 'nope' }, 'fallback')).toBe('nope')
  })

  it('falls back for null / empty / unrenderable detail', () => {
    expect(formatErrorDetail(null, 'fallback')).toBe('fallback')
    expect(formatErrorDetail(undefined, 'fallback')).toBe('fallback')
    expect(formatErrorDetail([], 'fallback')).toBe('fallback')
    expect(formatErrorDetail('', 'fallback')).toBe('fallback')
    expect(formatErrorDetail({ foo: 'bar' }, 'fallback')).toBe('fallback')
  })
})
