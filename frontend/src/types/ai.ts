export interface AIModel {
  modelId: string;
  provider: string;
  displayName: string;
  capabilities: Array<'chat' | 'tool' | 'vision' | 'long_context'>;
  priceTier: 'low' | 'medium' | 'high';
  enabled: boolean;
}

export interface AIMessage {
  messageId: string;
  conversationId: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  createdAt: string;
  citations?: Array<{ sourceId: string; title: string; snippet: string }>;
  toolCalls?: Array<{ toolName: string; argsSummary: string; status: 'pending' | 'confirmed' | 'rejected' | 'done' }>;
}

export interface AIConversation {
  conversationId: string;
  title: string;
  researchRunIds: string[];
  modelId: string;
  updatedAt: string;
}

export interface SendMessageRequest {
  content: string;
  modelId: string;
  /** 临时附加上下文（如当前页面选择） */
  attachedContext?: Record<string, unknown>;
}

export interface ConfirmActionRequest {
  toolCallId: string;
  approved: boolean;
}
