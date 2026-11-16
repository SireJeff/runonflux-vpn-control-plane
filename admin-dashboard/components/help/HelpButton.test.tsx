import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const mockPathname = vi.fn()
vi.mock('next/navigation', () => ({ usePathname: () => mockPathname() }))

import { HelpButton } from './HelpButton'

describe('HelpButton', () => {
  it('links to the mapped section for a known route', () => {
    mockPathname.mockReturnValue('/super/domains')
    render(<HelpButton />)
    expect(screen.getByRole('link', { name: 'Help for this page' })).toHaveAttribute(
      'href',
      '/super/help#6-tld--dns-management',
    )
  })

  it('renders nothing for an unmapped route', () => {
    mockPathname.mockReturnValue('/super/help')
    const { container } = render(<HelpButton />)
    expect(container).toBeEmptyDOMElement()
  })
})
