import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';

const apiMocks = vi.hoisted(() => ({
  fetchAIConfig: vi.fn(),
  saveAIConfig: vi.fn(),
}));

vi.mock('@/api/client', () => apiMocks);

import { AIConfigPage } from './AIConfigPage';

const emptyConfig = {
  providers: [],
  defaultModel: '',
  systemPrompt: '',
  temperature: 0.7,
  capabilities: {
    read_research: true,
    read_market: true,
    read_reports: true,
    query_database: true,
    use_chat_history: true,
    rag_corpus: false,
  },
  embeddingConfig: {
    provider: 'none' as const,
    baseUrl: '',
    model: '',
    apiKeyEnv: '',
    dimensions: 1024,
  },
  skills: [],
};

afterEach(async () => {
  vi.clearAllMocks();
  await i18n.changeLanguage('zh');
});

describe('AIConfigPage provider onboarding', () => {
  it('lets an English-language user add the first provider from an empty config', async () => {
    await i18n.changeLanguage('en');
    apiMocks.fetchAIConfig.mockResolvedValue(emptyConfig);

    render(<AIConfigPage />);

    expect(await screen.findByText('No providers')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Add provider/i }));
    fireEvent.click(screen.getByRole('button', { name: /Start blank/i }));

    expect(screen.getByText(/Editing: Custom provider/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('OPENAI_API_KEY')).toBeInTheDocument();
  });

  it('seeds base URL and env var from a preset, leaving models to be filled in', async () => {
    await i18n.changeLanguage('en');
    apiMocks.fetchAIConfig.mockResolvedValue(emptyConfig);

    render(<AIConfigPage />);

    expect(await screen.findByText('No providers')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Add provider/i }));
    fireEvent.click(screen.getByRole('button', { name: /DeepSeek/i }));

    expect(screen.getByText(/Editing: DeepSeek/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue('https://api.deepseek.com')).toBeInTheDocument();
    expect(screen.getByDisplayValue('DEEPSEEK_API_KEY')).toBeInTheDocument();
  });
});
