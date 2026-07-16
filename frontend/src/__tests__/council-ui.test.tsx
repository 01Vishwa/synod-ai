import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemberTabs } from '../components/council/MemberTabs';
import { RankingTable } from '../components/council/RankingTable';
import { ChairmanReport } from '../components/council/ChairmanReport';

describe('Council UI Regression Tests', () => {
  const members = [
    { member_id: 'm1', display_label: 'Member A', model_id: 'model1', provider: 'openrouter' },
    { member_id: 'm2', display_label: 'Member B', model_id: 'model2', provider: 'openrouter' },
    { member_id: 'm3', display_label: 'Member C', model_id: 'model3', provider: 'openrouter' }
  ];

  it('Test 1: Markdown response is rendered correctly without raw markers', () => {
    const responses = [
      {
        member_id: 'm1',
        stage: 'stage_1',
        content: '# Heading\n\n**Bold text**\n\n- Item one\n- Item two',
        latency_ms: 100,
        tokens_in: 10,
        tokens_out: 20,
        cost_usd: 0.01,
        error: null
      }
    ];

    const { container } = render(
      <MemberTabs members={[members[0]]} responses={responses} />
    );

    // ReactMarkdown will render headings, strong tags, and list items
    const heading = container.querySelector('h1');
    expect(heading).toBeInTheDocument();
    expect(heading?.textContent).toBe('Heading');

    const strong = container.querySelector('strong');
    expect(strong).toBeInTheDocument();
    expect(strong?.textContent).toBe('Bold text');

    const listItems = container.querySelectorAll('li');
    expect(listItems.length).toBe(2);
    
    // Ensure raw markers are not rendered as plain text
    expect(screen.queryByText('**Bold text**')).not.toBeInTheDocument();
    expect(screen.queryByText('# Heading')).not.toBeInTheDocument();
  });

  it('Test 2: Failed member C does not appear in aggregate ranking', () => {
    const aggregateScores = {
      'm1': 0.50,
      'm2': 0.50
    };
    const anonymizationMap = {
      'm1': 'Member A',
      'm2': 'Member B'
    };

    render(
      <RankingTable
        rankings={[]}
        aggregateScores={aggregateScores}
        members={members}
        anonymizationMap={anonymizationMap}
        stage2Status="completed"
      />
    );

    // Member A and B are rendered in rankings
    expect(screen.getByText('Member A')).toBeInTheDocument();
    expect(screen.getByText('Member B')).toBeInTheDocument();
    
    // Member C is completely absent from the leaderboard
    expect(screen.queryByText('Member C')).not.toBeInTheDocument();
  });

  it('Test 3: Failed member C does not appear in Peer Justifications and no "Reviewing..."', () => {
    const rankings = [
      { ranked_by_member_id: 'm1', ranking_order: ['Member B', 'Member A'], justification: 'A reviewed B' },
      { ranked_by_member_id: 'm2', ranking_order: ['Member A', 'Member B'], justification: 'B reviewed A' }
    ];
    const aggregateScores = { 'm1': 0.50, 'm2': 0.50 };
    const anonymizationMap = { 'm1': 'Member A', 'm2': 'Member B' };

    render(
      <RankingTable
        rankings={rankings}
        aggregateScores={aggregateScores}
        members={members}
        anonymizationMap={anonymizationMap}
        stage2Status="completed"
      />
    );

    // Member A and B's review results are present
    expect(screen.getByText(/A reviewed B/)).toBeInTheDocument();
    expect(screen.getByText(/B reviewed A/)).toBeInTheDocument();

    // Member C is absent
    expect(screen.queryByText('Member C')).not.toBeInTheDocument();

    // No reviewing placeholder for C
    expect(screen.queryByText('◌ Reviewing…')).not.toBeInTheDocument();
  });

  it('Test 4: Session page does not render Langfuse trace link', () => {
    render(
      <ChairmanReport
        reportMd="Final synthesis"
        citations={[]}
        members={members}
        stage1Responses={[]}
        aggregateScores={{}}
        chairmanMemberId="m1"
        traceId="mock-trace-id-123"
        stage3Status="completed"
      />
    );

    // The Langfuse trace anchor should not exist
    expect(screen.queryByText('View full Langfuse trace →')).not.toBeInTheDocument();
    const links = screen.queryAllByRole('link');
    const traceLink = links.find(l => l.getAttribute('href')?.includes('mock-trace-id-123'));
    expect(traceLink).toBeUndefined();
  });
});
