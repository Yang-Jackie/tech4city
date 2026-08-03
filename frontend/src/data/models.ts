export type AnalysisResult = {
  harmful: boolean;
  category: string;
  severity: "None" | "Low" | "Medium" | "High" | "Urgent";
  confidence?: number;
  explanation: string;
  analyzedAt: string;
  pipelineVersion?: string;
};

export type Message = {
  id: string;
  direction: "incoming" | "outgoing";
  text: string;
  time: string;
  flagged?: boolean;
  analysis?: AnalysisResult;
  analysisState?: "pending" | "processing" | "completed" | "failed";
};

export type Conversation = {
  id: string;
  name: string;
  initials: string;
  avatarClass: string;
  lastActive: string;
  preview: string;
  unread?: number;
  flaggedCount?: number;
  messages: Message[];
};
