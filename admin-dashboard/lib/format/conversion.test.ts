import { describe, it, expect } from 'vitest'
import { usdToTomans, tomansToUsd } from './conversion'

describe('conversion', () => {
  it('usdToTomans rounds to whole Tomans', () => {
    expect(usdToTomans(50, 60000)).toBe(3000000)
  })
  it('tomansToUsd returns 2dp', () => {
    expect(tomansToUsd(3000000, 60000)).toBe(50)
    expect(tomansToUsd(100000, 60000)).toBe(1.67)
  })
  it('guards zero/invalid rate', () => {
    expect(tomansToUsd(100, 0)).toBe(0)
    expect(usdToTomans(10, 0)).toBe(0)
  })
})
