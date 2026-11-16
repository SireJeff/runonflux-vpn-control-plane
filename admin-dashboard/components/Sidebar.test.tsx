import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('next/navigation', () => ({ usePathname: () => '/dashboard/wallet' }))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { username: 'reseller', display_name: 'Reseller' }, logout: vi.fn() }),
}))

import { Sidebar, Header } from './Sidebar'

describe('reseller shell wiring', () => {
  it('sidebar has a Help nav link', () => {
    render(<Sidebar />)
    expect(screen.getByRole('link', { name: 'Help' })).toHaveAttribute('href', '/dashboard/help')
  })

  it('header shows a route-aware HelpButton', () => {
    render(<Header />)
    expect(screen.getByRole('link', { name: 'Help for this page' })).toHaveAttribute(
      'href',
      '/dashboard/help#3-wallet--billing',
    )
  })
})
