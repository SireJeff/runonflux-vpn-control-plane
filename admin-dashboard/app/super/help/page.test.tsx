import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import SuperHelpPage from './page'

describe('SuperHelpPage', () => {
  it('renders the runbook heading and guide content', () => {
    render(<SuperHelpPage />)
    expect(screen.getByRole('heading', { name: /Help & Runbook/i })).toBeInTheDocument()
    // The superadmin guide contains a "Managing Resellers" section heading.
    expect(
      screen.getAllByText(/Managing Resellers/i).length,
    ).toBeGreaterThan(0)
  })
})
