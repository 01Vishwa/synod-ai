import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { SearchableSelect } from '../components/ui/SearchableSelect';
import { MemberCard } from '../app/page'; // or wherever MemberCard is

describe('Model Search Normalization', () => {
  const options = [
    {
      value: 'openai/gpt-oss-20b:free',
      label: 'OpenAI: gpt-oss-20b (free)',
    },
    {
      value: 'google/gemma-4-31b-it:free',
      label: 'Google: gemma-4-31b-it (free)',
    }
  ];

  const testSearch = (query: string, expectedFound: string, expectedMissing: string) => {
    render(
      <SearchableSelect
        value=""
        options={options}
        onChange={() => {}}
      />
    );
    
    // Open dropdown
    fireEvent.click(screen.getByRole('button'));
    
    // Type query
    const input = screen.getByPlaceholderText('Search...');
    fireEvent.change(input, { target: { value: query } });
    
    // Verify matching
    expect(screen.getByText(expectedFound)).toBeInTheDocument();
    expect(screen.queryByText(expectedMissing)).not.toBeInTheDocument();
  };

  it('matches full canonical ID', () => {
    testSearch('openai/gpt-oss-20b:free', 'OpenAI: gpt-oss-20b (free)', 'Google: gemma-4-31b-it (free)');
  });

  it('matches slug with colon', () => {
    testSearch('gpt-oss-20b:free', 'OpenAI: gpt-oss-20b (free)', 'Google: gemma-4-31b-it (free)');
  });

  it('matches slug without free suffix', () => {
    testSearch('gpt-oss-20b', 'OpenAI: gpt-oss-20b (free)', 'Google: gemma-4-31b-it (free)');
  });

  it('matches spaced out query', () => {
    testSearch('gpt oss 20b', 'OpenAI: gpt-oss-20b (free)', 'Google: gemma-4-31b-it (free)');
  });

  it('matches uppercase spaced out query', () => {
    testSearch('GPT OSS 20B', 'OpenAI: gpt-oss-20b (free)', 'Google: gemma-4-31b-it (free)');
  });

  it('matches provider and slug spaced out', () => {
    testSearch('OpenAI GPT OSS 20B', 'OpenAI: gpt-oss-20b (free)', 'Google: gemma-4-31b-it (free)');
  });

  it('does not match unrelated queries', () => {
    testSearch('gemma 31b', 'Google: gemma-4-31b-it (free)', 'OpenAI: gpt-oss-20b (free)');
  });
});

describe('Model Selection & Provider Filtering', () => {
  it('preserves the exact canonical model ID on selection', () => {
    const onChange = jest.fn();
    render(
      <SearchableSelect
        value=""
        options={[{ value: 'openai/gpt-oss-20b:free', label: 'OpenAI: gpt-oss-20b (free)' }]}
        onChange={onChange}
      />
    );
    
    fireEvent.click(screen.getByRole('button'));
    fireEvent.click(screen.getByText('OpenAI: gpt-oss-20b (free)'));
    
    // Exact canonical ID returned, no modifications
    expect(onChange).toHaveBeenCalledWith('openai/gpt-oss-20b:free');
  });
});
