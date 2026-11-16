import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'

describe('test harness', () => {
  it('renders a component and applies jest-dom matchers', () => {
    render(<button>Ping</button>)
    expect(screen.getByRole('button', { name: 'Ping' })).toBeInTheDocument()
  })
})
