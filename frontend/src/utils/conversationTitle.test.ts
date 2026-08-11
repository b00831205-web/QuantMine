import { describe, expect, it } from 'vitest';
import { localizeConversationTitle } from './conversationTitle';

describe('localizeConversationTitle', () => {
  it('localizes current and legacy default titles', () => {
    expect(localizeConversationTitle('New chat', 'New conversation')).toBe('New conversation');
    expect(localizeConversationTitle('新对话', 'New conversation')).toBe('New conversation');
    expect(localizeConversationTitle('New chat', '新对话')).toBe('新对话');
  });

  it('preserves generated conversation titles', () => {
    expect(localizeConversationTitle('Factor IC analysis', 'New conversation')).toBe(
      'Factor IC analysis',
    );
  });
});
