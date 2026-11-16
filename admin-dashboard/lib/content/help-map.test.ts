import { describe, it, expect } from 'vitest'
import { parseToc } from '@/lib/help/toc'
import superadminGuide from '@/content/guides/superadmin-guide'
import subadminGuide from '@/content/guides/subadmin-guide'
import { superHelpMap, dashboardHelpMap, helpAnchorForPath } from './help-map'

const superSlugs = new Set(parseToc(superadminGuide).map((e) => e.slug))
const subSlugs = new Set(parseToc(subadminGuide).map((e) => e.slug))

describe('help-map integrity', () => {
  it('every super anchor is a real heading slug in the superadmin guide', () => {
    for (const anchor of Object.values(superHelpMap)) {
      expect(superSlugs.has(anchor), `missing super anchor: ${anchor}`).toBe(true)
    }
  })

  it('every dashboard anchor is a real heading slug in the subadmin guide', () => {
    for (const anchor of Object.values(dashboardHelpMap)) {
      expect(subSlugs.has(anchor), `missing dashboard anchor: ${anchor}`).toBe(true)
    }
  })
})

describe('helpAnchorForPath', () => {
  it('maps a super route to its section', () => {
    expect(helpAnchorForPath('/super/domains')).toEqual({ href: '/super/help#6-tld--dns-management' })
  })
  it('maps a dashboard route to its section', () => {
    expect(helpAnchorForPath('/dashboard/wallet')).toEqual({ href: '/dashboard/help#3-wallet--billing' })
  })
  it('returns null for unmapped routes', () => {
    expect(helpAnchorForPath('/super/help')).toBeNull()
    expect(helpAnchorForPath('/user/connections')).toBeNull()
  })
})
