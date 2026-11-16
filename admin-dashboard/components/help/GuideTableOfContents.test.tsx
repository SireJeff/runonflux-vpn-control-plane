import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { GuideTableOfContents } from './GuideTableOfContents'

describe('GuideTableOfContents', () => {
  it('renders anchor links to heading slugs', () => {
    render(
      <GuideTableOfContents
        content={'## 4. Managing Resellers\n### 4.1 Approve a reseller\n'}
      />,
    )
    const top = screen.getByRole('link', { name: '4. Managing Resellers' })
    expect(top).toHaveAttribute('href', '#4-managing-resellers')
    expect(
      screen.getByRole('link', { name: '4.1 Approve a reseller' }),
    ).toHaveAttribute('href', '#41-approve-a-reseller')
  })

  it('labels the nav landmark for assistive tech', () => {
    render(<GuideTableOfContents content={'## Section One\n'} />)
    expect(screen.getByRole('navigation', { name: 'Table of contents' })).toBeInTheDocument()
  })

  it('filters entries by the search box', async () => {
    const { default: userEvent } = await import('@testing-library/user-event')
    render(
      <GuideTableOfContents content={'## Wallet & Billing\n## Managing End-Users\n'} />,
    )
    await userEvent.type(screen.getByRole('textbox'), 'wallet')
    expect(screen.getByRole('link', { name: 'Wallet & Billing' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Managing End-Users' })).not.toBeInTheDocument()
  })
})
