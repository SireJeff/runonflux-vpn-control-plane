import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import DashboardHelpPage from './page'

describe('DashboardHelpPage', () => {
  it('renders the runbook heading and reseller guide content', () => {
    render(<DashboardHelpPage />)
    expect(screen.getByRole('heading', { name: /Help & Runbook/i })).toBeInTheDocument()
    // "Wallet & Billing" appears in subadmin-guide but NOT in superadmin-guide,
    // so this assertion fails if the wrong guide module is ever imported.
    expect(
      screen.getAllByText(/Wallet & Billing/i).length,
    ).toBeGreaterThan(0)
  })
})
