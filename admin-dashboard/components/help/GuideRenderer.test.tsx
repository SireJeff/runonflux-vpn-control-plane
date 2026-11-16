import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { GuideRenderer } from './GuideRenderer'

describe('GuideRenderer', () => {
  it('renders headings with slug ids', () => {
    render(<GuideRenderer content={'## Wire Orders & Platform Settings\n'} />)
    const heading = screen.getByRole('heading', { name: 'Wire Orders & Platform Settings' })
    expect(heading).toHaveAttribute('id', 'wire-orders--platform-settings')
  })

  it('renders GFM tables', () => {
    render(<GuideRenderer content={'| A | B |\n|---|---|\n| 1 | 2 |\n'} />)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '1' })).toBeInTheDocument()
  })
})
