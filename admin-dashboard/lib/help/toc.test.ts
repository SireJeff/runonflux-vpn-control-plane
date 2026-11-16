import { describe, it, expect } from 'vitest'
import { parseToc } from './toc'

describe('parseToc', () => {
  it('extracts ## and ### headings with github-slugger ids', () => {
    const md = [
      '# Title (ignored)',
      '',
      '## 4. Managing Resellers',
      'body',
      '### 4.1 How do I approve a pending reseller?',
      '## 6. TLD & DNS Management',
    ].join('\n')
    expect(parseToc(md)).toEqual([
      { depth: 2, text: '4. Managing Resellers', slug: '4-managing-resellers' },
      {
        depth: 3,
        text: '4.1 How do I approve a pending reseller?',
        slug: '41-how-do-i-approve-a-pending-reseller',
      },
      { depth: 2, text: '6. TLD & DNS Management', slug: '6-tld--dns-management' },
    ])
  })

  it('ignores ## inside fenced code blocks', () => {
    const md = ['## Real', '', '```', '## not a heading', '```', ''].join('\n')
    expect(parseToc(md)).toEqual([{ depth: 2, text: 'Real', slug: 'real' }])
  })
})
