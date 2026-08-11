const UNTITLED_CONVERSATION_TITLES = new Set(['New chat', '新对话']);

/** Render backend default markers through the active frontend locale. */
export function localizeConversationTitle(title: string, localizedDefault: string): string {
  return UNTITLED_CONVERSATION_TITLES.has(title) ? localizedDefault : title;
}
