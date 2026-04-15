/**
 * Nexus Store — Zustand state management
 */

import { create } from "zustand";
import {
  api,
  type Notebook,
  type Source,
  type ChatMessage,
  type ChatSession,
  type Artifact,
  type ResearchResult,
  type ResearchSession,
  type FlashCard,
} from "@/lib/api";

// ── App Store ────────────────────────────────────────────────

interface AppState {
  // Notebooks
  notebooks: Notebook[];
  activeNotebook: (Notebook & { sources?: Source[] }) | null;
  loadingNotebooks: boolean;

  // Chat
  chatMessages: ChatMessage[];
  activeChatSession: ChatSession | null;
  chatSessions: ChatSession[];
  chatLoading: boolean;

  // Research
  researchAnswer: ResearchResult | null;
  researchSessions: ResearchSession[];
  activeResearchSessionId: string | null;
  researchLoading: boolean;

  // Flashcards
  flashcards: FlashCard[];
  activeCardIndex: number;
  showAnswer: boolean;

  // Artifacts
  artifacts: Artifact[];

  // UI
  sidebarOpen: boolean;
  activeTab: "sources" | "chat" | "studio" | "notes" | "research" | "brain" | "settings";
  uploadingFile: boolean;

  // Actions
  fetchNotebooks: () => Promise<void>;
  selectNotebook: (id: string) => Promise<void>;
  createNotebook: (data: Partial<Notebook>) => Promise<Notebook>;
  deleteNotebook: (id: string) => Promise<void>;

  fetchChatSessions: (notebookId?: string) => Promise<void>;
  selectChatSession: (session: ChatSession) => Promise<void>;
  sendChatMessage: (content: string) => Promise<void>;
  clearChat: () => void;

  fetchArtifacts: (notebookId?: string) => Promise<void>;
  createArtifact: (data: {
    notebook_id: string;
    title: string;
    artifact_type: string;
    generation_config?: Record<string, unknown>;
  }) => Promise<Artifact>;

  sendResearchQuery: (query: string) => Promise<void>;
  fetchResearchSessions: (notebookId?: string) => Promise<void>;

  fetchFlashcards: (notebookId?: string) => Promise<void>;
  reviewFlashcard: (id: string, rating: number) => Promise<void>;
  nextCard: () => void;
  toggleAnswer: () => void;

  uploadFile: (file: File) => Promise<void>;
  exportArtifact: (artifactId: string, format: string) => Promise<void>;

  toggleSidebar: () => void;
  setActiveTab: (tab: AppState["activeTab"]) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  notebooks: [],
  activeNotebook: null,
  loadingNotebooks: false,
  chatMessages: [],
  activeChatSession: null,
  chatSessions: [],
  chatLoading: false,
  researchAnswer: null,
  researchSessions: [],
  activeResearchSessionId: null,
  researchLoading: false,
  flashcards: [],
  activeCardIndex: 0,
  showAnswer: false,
  artifacts: [],
  sidebarOpen: true,
  activeTab: "sources",
  uploadingFile: false,

  fetchNotebooks: async () => {
    set({ loadingNotebooks: true });
    try {
      const notebooks = await api.listNotebooks();
      set({ notebooks, loadingNotebooks: false });
    } catch (error) {
      console.error("Failed to fetch notebooks:", error);
      set({ loadingNotebooks: false });
    }
  },

  selectNotebook: async (id: string) => {
    try {
      const notebook = await api.getNotebook(id);
      set({
        activeNotebook: notebook,
        chatMessages: [],
        activeChatSession: null,
        researchAnswer: null,
        activeResearchSessionId: null,
        activeTab: "sources",
      });
      get().fetchChatSessions(id);
      get().fetchArtifacts(id);
      get().fetchResearchSessions(id);
    } catch (error) {
      console.error("Failed to fetch notebook:", error);
    }
  },

  createNotebook: async (data) => {
    const notebook = await api.createNotebook(data);
    set({ notebooks: [...get().notebooks, notebook] });
    return notebook;
  },

  deleteNotebook: async (id: string) => {
    await api.deleteNotebook(id);
    set({
      notebooks: get().notebooks.filter((n) => n.id !== id),
      activeNotebook: get().activeNotebook?.id === id ? null : get().activeNotebook,
    });
  },

  fetchChatSessions: async (notebookId?: string) => {
    try {
      const sessions = await api.listSessions(notebookId);
      set({ chatSessions: sessions });
    } catch (error) {
      console.error("Failed to fetch sessions:", error);
    }
  },

  selectChatSession: async (session: ChatSession) => {
    set({ activeChatSession: session, chatLoading: true });
    try {
      const messages = await api.getSessionMessages(session.id);
      set({ chatMessages: messages, chatLoading: false });
    } catch (error) {
      console.error("Failed to fetch messages:", error);
      set({ chatLoading: false });
    }
  },

  sendChatMessage: async (content: string) => {
    const { activeNotebook, activeChatSession, chatMessages } = get();
    const userMessage: ChatMessage = { role: "user", content };
    set({ chatMessages: [...chatMessages, userMessage], chatLoading: true });

    try {
      const response = await api.sendMessage({
        content,
        session_id: activeChatSession?.id,
        notebook_id: activeNotebook?.id,
        stream: false,
      });
      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: response.content,
        turn_number: response.turn_number,
        citations: response.citations,
      };
      set({
        chatMessages: [...get().chatMessages, assistantMessage],
        chatLoading: false,
        activeChatSession: activeChatSession || {
          id: response.session_id,
          title: content.slice(0, 50),
          message_count: 2,
          created_at: new Date().toISOString(),
        },
      });
    } catch (error) {
      console.error("Chat error:", error);
      set({
        chatMessages: [
          ...get().chatMessages,
          { role: "assistant", content: "Sorry, an error occurred. Please try again." },
        ],
        chatLoading: false,
      });
    }
  },

  clearChat: () => set({ chatMessages: [], activeChatSession: null }),

  sendResearchQuery: async (query: string) => {
    const { activeNotebook, activeResearchSessionId } = get();
    set({ researchLoading: true });
    try {
      const result = await api.researchQuery({
        query,
        session_id: activeResearchSessionId || undefined,
        notebook_id: activeNotebook?.id,
      });
      set({
        researchAnswer: result,
        activeResearchSessionId: result.session_id,
        researchLoading: false,
      });
    } catch (error) {
      console.error("Research error:", error);
      set({ researchLoading: false });
    }
  },

  fetchResearchSessions: async (notebookId?: string) => {
    try {
      const sessions = await api.listResearchSessions(notebookId);
      set({ researchSessions: sessions });
    } catch (error) {
      console.error("Failed to fetch research sessions:", error);
    }
  },

  fetchFlashcards: async (notebookId?: string) => {
    try {
      const cards = await api.getDueFlashcards(notebookId);
      set({ flashcards: cards, activeCardIndex: 0, showAnswer: false });
    } catch (error) {
      console.error("Failed to fetch flashcards:", error);
    }
  },

  reviewFlashcard: async (id: string, rating: number) => {
    try {
      await api.reviewFlashcard(id, rating);
      const cards = get().flashcards.filter((c) => c.id !== id);
      set({ flashcards: cards, showAnswer: false });
    } catch (error) {
      console.error("Review failed:", error);
    }
  },

  nextCard: () =>
    set((s) => ({
      activeCardIndex: Math.min(s.activeCardIndex + 1, s.flashcards.length - 1),
      showAnswer: false,
    })),

  toggleAnswer: () => set((s) => ({ showAnswer: !s.showAnswer })),

  uploadFile: async (file: File) => {
    const { activeNotebook } = get();
    set({ uploadingFile: true });
    try {
      await api.uploadSource(file, activeNotebook?.id);
      if (activeNotebook) get().selectNotebook(activeNotebook.id);
      set({ uploadingFile: false });
    } catch (error) {
      console.error("Upload failed:", error);
      set({ uploadingFile: false });
    }
  },

  exportArtifact: async (artifactId: string, format: string) => {
    try {
      const blob = await api.exportContent({ artifact_id: artifactId, format });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `export.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Export failed:", error);
    }
  },

  fetchArtifacts: async (notebookId?: string) => {
    try {
      const artifacts = await api.listArtifacts(notebookId);
      set({ artifacts });
    } catch (error) {
      console.error("Failed to fetch artifacts:", error);
    }
  },

  createArtifact: async (data) => {
    const artifact = await api.createArtifact(data);
    set({ artifacts: [...get().artifacts, artifact] });
    return artifact;
  },

  toggleSidebar: () => set({ sidebarOpen: !get().sidebarOpen }),
  setActiveTab: (tab) => set({ activeTab: tab }),
}));
