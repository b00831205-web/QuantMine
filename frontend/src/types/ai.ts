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
  /** 高影响操作确认请求（消息附属字段） */
  confirmRequest?: AIConfirmRequest;
    attachments?: Array<{
    attachmentId: string;
    filename: string;
    kind: 'image' | 'text' | 'document' | 'unsupported';
  }>;
}

export interface AIConfirmRequest {
  toolCallId: string;
  title: string;
  description: string;
  status: 'pending' | 'confirmed' | 'rejected';
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
  attachements?: Array<{attachmentId: string}>;
}

export interface ConfirmActionRequest {
  toolCallId: string;
  approved: boolean;
}

/** AI 配置（参考 Dify 供应商管理，简化版） */
export interface AIProviderConfig {
  providerId: string;
  name: string;
  configured: boolean;
  baseUrl: string;
  models: string[];
  capabilities?: Partial<AICapabilities> | undefined;
  /** API Key 所在的环境变量名；缺省 OPENAI_API_KEY */
  apiKeyEnv?: string;
}

export interface AIConfig {
  providers: AIProviderConfig[];
  defaultModel: string;
  systemPrompt: string;
  temperature: number;
  capabilities: AICapabilities;
  embeddingConfig: AIEmbeddingConfig;
}

export interface AICapabilities{
  read_research: boolean;
  read_market: boolean;
  read_reports: boolean;
  query_database: boolean;
  use_chat_history: boolean;
  rag_corpus: boolean;
}

export interface AIEmbeddingConfig{
  provider: 'none' | 'openai_compatible' | 'ollama';
  baseUrl : string;
  model: string;
  apiKeyEnv? : string;
  dimensions: number;
  configured?: boolean;
}

export interface AISkill {
  name: string;
  displayName: string;
  description: string;
  enabled: boolean;
}

export interface AIConfig {
  providers: AIProviderConfig[];
  defaultModel: string;
  systemPrompt: string;
  temperature: number;
  capabilities: AICapabilities;
  embeddingConfig: AIEmbeddingConfig;
  skills: AISkill[];
}
