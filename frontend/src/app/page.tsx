"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "@/lib/store";
import { api, type PodcastPresetCatalog } from "@/lib/api";
import { ResearchPanel } from "@/components/ResearchPanel";
import { NotesPanel } from "@/components/NotesPanel";
import { SettingsPanel } from "@/components/SettingsPanel";
import { cn, formatRelativeTime, truncate } from "@/lib/utils";
import {
  BookOpen,
  MessageSquare,
  Sparkles,
  FileText,
  Plus,
  Search,
  Settings,
  PanelLeftClose,
  PanelLeft,
  Mic,
  FileQuestion,
  Layers,
  Trash2,
  Pin,
  MoreHorizontal,
  Send,
  Loader2,
  Upload,
  Link,
  Globe,
  ChevronDown,
  Zap,
  Brain,
  Download,
  FlaskConical,
} from "lucide-react";

// ── Sidebar Component ────────────────────────────────────────

function Sidebar() {
  const {
    notebooks,
    activeNotebook,
    loadingNotebooks,
    sidebarOpen,
    fetchNotebooks,
    selectNotebook,
    toggleSidebar,
  } = useAppStore();

  const [searchQuery, setSearchQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    fetchNotebooks();
  }, [fetchNotebooks]);

  const filteredNotebooks = notebooks.filter((n) =>
    n.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleCreate = async () => {
    if (!newName.trim()) return;
    const { createNotebook } = useAppStore.getState();
    const nb = await createNotebook({
      name: newName,
      description: "",
      icon: "📓",
      color: "#6366f1",
      tags: [],
    });
    selectNotebook(nb.id);
    setNewName("");
    setShowCreate(false);
  };

  if (!sidebarOpen) {
    return (
      <div className="w-12 border-r border-border bg-card/50 flex flex-col items-center py-4 gap-4">
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-all"
        >
          <PanelLeft className="w-4 h-4" />
        </button>
        <div className="h-px w-6 bg-border" />
        {notebooks.slice(0, 5).map((nb) => (
          <button
            key={nb.id}
            onClick={() => selectNotebook(nb.id)}
            className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center text-sm transition-all",
              activeNotebook?.id === nb.id
                ? "bg-primary text-primary-foreground shadow-md"
                : "hover:bg-accent text-muted-foreground"
            )}
            title={nb.name}
          >
            {nb.icon || "📓"}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="w-72 border-r border-border bg-card/50 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 flex items-center justify-between border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center">
            <Brain className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold gradient-text">Nexus</h1>
            <p className="text-[10px] text-muted-foreground tracking-wider uppercase">
              Notebook 11 LM
            </p>
          </div>
        </div>
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-all"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Search */}
      <div className="p-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search notebooks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-8 pl-9 pr-3 rounded-lg bg-secondary/50 border border-border text-sm
                       placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30
                       transition-all"
          />
        </div>
      </div>

      {/* Notebook List */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        <div className="flex items-center justify-between px-2 py-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Notebooks
          </span>
          <button
            onClick={() => setShowCreate(true)}
            className="p-1 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="mx-2 mb-2 p-2 rounded-lg bg-primary/5 border border-primary/20 animate-slide-in">
            <input
              type="text"
              placeholder="Notebook name..."
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
              className="w-full h-7 px-2 rounded-md bg-background border border-border text-sm
                         focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            <div className="flex gap-1 mt-1.5">
              <button
                onClick={handleCreate}
                className="flex-1 h-6 rounded-md bg-primary text-primary-foreground text-xs font-medium
                           hover:bg-primary/90 transition-all"
              >
                Create
              </button>
              <button
                onClick={() => {
                  setShowCreate(false);
                  setNewName("");
                }}
                className="h-6 px-2 rounded-md text-xs text-muted-foreground hover:bg-accent transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {loadingNotebooks ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : filteredNotebooks.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p>No notebooks yet</p>
            <button
              onClick={() => setShowCreate(true)}
              className="text-primary text-xs mt-1 hover:underline"
            >
              Create your first notebook
            </button>
          </div>
        ) : (
          filteredNotebooks.map((nb) => (
            <button
              key={nb.id}
              onClick={() => selectNotebook(nb.id)}
              className={cn(
                "sidebar-item w-full",
                activeNotebook?.id === nb.id && "active"
              )}
            >
              <span className="text-base">{nb.icon || "📓"}</span>
              <div className="flex-1 text-left min-w-0">
                <p className="truncate text-sm">{nb.name}</p>
                <p className="text-[10px] text-muted-foreground">
                  {nb.source_count} source{nb.source_count !== 1 ? "s" : ""} ·{" "}
                  {formatRelativeTime(nb.updated_at)}
                </p>
              </div>
              {nb.pinned && <Pin className="w-3 h-3 text-primary/60 shrink-0" />}
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-border">
        <button className="sidebar-item w-full">
          <Settings className="w-4 h-4" />
          <span>Settings</span>
        </button>
      </div>
    </div>
  );
}

// ── Tab Navigation ───────────────────────────────────────────

function TabNav() {
  const { activeTab, setActiveTab } = useAppStore();

  const tabs = [
    { id: "sources" as const, label: "Sources", icon: FileText },
    { id: "chat" as const, label: "Chat", icon: MessageSquare },
    { id: "studio" as const, label: "Studio", icon: Sparkles },
    { id: "research" as const, label: "Research", icon: FlaskConical },
    { id: "notes" as const, label: "Notes", icon: Layers },
  ];

  return (
    <div className="flex border-b border-border bg-card/30">
      {tabs.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => setActiveTab(id)}
          className={cn(
            "flex items-center gap-2 px-5 py-3 text-sm font-medium transition-all relative",
            activeTab === id
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Icon className="w-4 h-4" />
          {label}
          {activeTab === id && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
          )}
        </button>
      ))}
    </div>
  );
}

// ── Sources Panel ────────────────────────────────────────────

function SourcesPanel() {
  const { activeNotebook, uploadFile, uploadingFile } = useAppStore();
  const sources = (activeNotebook as any)?.sources || [];
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFileSelect = useCallback((files: FileList | null) => {
    if (!files?.length) return;
    Array.from(files).forEach((f) => uploadFile(f));
  }, [uploadFile]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    handleFileSelect(e.dataTransfer.files);
  }, [handleFileSelect]);

  return (
    <div
      className={cn("flex-1 overflow-y-auto p-6", dragging && "ring-2 ring-primary ring-inset rounded-lg")}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.txt,.md,.csv"
        className="hidden"
        onChange={(e) => handleFileSelect(e.target.files)}
      />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold">Sources</h2>
          <p className="text-sm text-muted-foreground">
            {sources.length} source{sources.length !== 1 ? "s" : ""} added
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadingFile}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/10 text-primary text-sm font-medium hover:bg-primary/20 transition-all"
          >
            {uploadingFile ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            Upload
          </button>
          <button className="flex items-center gap-2 px-3 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium hover:bg-secondary/80 transition-all">
            <Link className="w-4 h-4" />
            URL
          </button>
        </div>
      </div>

      {sources.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Globe className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
          <h3 className="text-lg font-semibold mb-2">No sources yet</h3>
          <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">
            Upload PDFs, paste text, or add URLs to build your knowledge base.
            Nexus will analyze and index everything automatically.
          </p>
          <div className="flex gap-3 justify-center">
            <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-all shadow-lg shadow-primary/25">
              <Upload className="w-4 h-4" />
              Upload File
            </button>
            <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-all">
              <FileText className="w-4 h-4" />
              Paste Text
            </button>
          </div>
        </div>
      ) : (
        <div className="grid gap-3">
          {sources.map((source: any) => (
            <div
              key={source.id}
              className="glass-card p-4 flex items-start gap-4"
            >
              <div
                className={cn(
                  "w-10 h-10 rounded-lg flex items-center justify-center shrink-0",
                  source.status === "ready"
                    ? "bg-green-500/10 text-green-500"
                    : source.status === "processing"
                    ? "bg-yellow-500/10 text-yellow-500"
                    : "bg-muted text-muted-foreground"
                )}
              >
                <FileText className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-medium truncate">{source.title}</h4>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-muted-foreground">
                    {source.source_type}
                  </span>
                  {source.word_count > 0 && (
                    <>
                      <span className="text-muted-foreground/30">·</span>
                      <span className="text-xs text-muted-foreground">
                        {source.word_count.toLocaleString()} words
                      </span>
                    </>
                  )}
                  <span className="text-muted-foreground/30">·</span>
                  <span
                    className={cn(
                      "text-xs px-1.5 py-0.5 rounded-full font-medium",
                      source.status === "ready"
                        ? "bg-green-500/10 text-green-600"
                        : source.status === "processing"
                        ? "bg-yellow-500/10 text-yellow-600"
                        : "bg-red-500/10 text-red-600"
                    )}
                  >
                    {source.status}
                  </span>
                </div>
                {source.topics?.length > 0 && (
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {source.topics.slice(0, 4).map((topic: string) => (
                      <span
                        key={topic}
                        className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all shrink-0">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Chat Panel ───────────────────────────────────────────────

function ChatPanel() {
  const { chatMessages, chatLoading, sendChatMessage } = useAppStore();
  const [input, setInput] = useState("");

  const handleSend = async () => {
    if (!input.trim() || chatLoading) return;
    const msg = input;
    setInput("");
    await sendChatMessage(msg);
  };

  return (
    <div className="flex-1 flex flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6">
        {chatMessages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-purple-500/20 flex items-center justify-center mx-auto mb-4">
                <Zap className="w-8 h-8 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mb-2">Ask about your sources</h3>
              <p className="text-sm text-muted-foreground mb-6">
                Ask questions, get summaries, or explore insights from your uploaded content.
                Every answer is grounded in your sources with citations.
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {[
                  "Summarize the key ideas",
                  "What are the main arguments?",
                  "Compare the perspectives",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="text-xs px-3 py-1.5 rounded-full border border-border
                               hover:bg-primary/10 hover:border-primary/30 hover:text-primary
                               transition-all"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto">
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className={cn(
                  "chat-message flex gap-3",
                  msg.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                {msg.role === "assistant" && (
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center shrink-0 mt-0.5">
                    <Sparkles className="w-4 h-4 text-white" />
                  </div>
                )}
                <div
                  className={cn(
                    "max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-br-md"
                      : "bg-card border border-border rounded-bl-md"
                  )}
                >
                  {msg.content}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-border/50">
                      <p className="text-[10px] font-semibold text-muted-foreground mb-1">Sources</p>
                      {msg.citations.map((c, j) => (
                        <p key={j} className="text-[10px] text-muted-foreground">
                          [{j + 1}] {c.source_title}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
                {msg.role === "user" && (
                  <div className="w-8 h-8 rounded-lg bg-secondary flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-xs font-bold">You</span>
                  </div>
                )}
              </div>
            ))}
            {chatLoading && (
              <div className="flex gap-3 animate-fade-in">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center shrink-0">
                  <Sparkles className="w-4 h-4 text-white animate-pulse" />
                </div>
                <div className="bg-card border border-border rounded-2xl rounded-bl-md px-4 py-3">
                  <div className="typing-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 border-t border-border">
        <div className="max-w-3xl mx-auto flex gap-2">
          <div className="flex-1 relative">
            <input
              type="text"
              placeholder="Ask about your sources..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              className="w-full h-11 px-4 rounded-xl bg-secondary/50 border border-border text-sm
                         placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30
                         focus:border-primary/50 transition-all"
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim() || chatLoading}
            className={cn(
              "w-11 h-11 rounded-xl flex items-center justify-center transition-all",
              input.trim()
                ? "bg-primary text-primary-foreground shadow-lg shadow-primary/25 hover:bg-primary/90"
                : "bg-secondary text-muted-foreground"
            )}
          >
            {chatLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Studio Panel ─────────────────────────────────────────────

function StudioPanel() {
  const { activeNotebook, artifacts, createArtifact } = useAppStore();
  const [presetCatalog, setPresetCatalog] = useState<PodcastPresetCatalog | null>(null);
  const [podcastPreset, setPodcastPreset] = useState({
    format: "conversational",
    length: "medium",
    language: "English",
    speaker_profile: "expert_student",
    speech_rate: 1.0,
  });
  const [loadingPresets, setLoadingPresets] = useState(false);

  useEffect(() => {
    let mounted = true;

    const loadPresets = async () => {
      setLoadingPresets(true);
      try {
        const catalog = await api.getPodcastPresets();
        if (!mounted) return;
        setPresetCatalog(catalog);
        setPodcastPreset({
          format: catalog.default.format,
          length: catalog.default.length,
          language: catalog.default.language,
          speaker_profile: catalog.default.speaker_profile,
          speech_rate: catalog.default.speech_rate,
        });
      } catch (error) {
        console.error("Failed to load podcast presets:", error);
      } finally {
        if (mounted) setLoadingPresets(false);
      }
    };

    loadPresets();
    return () => {
      mounted = false;
    };
  }, []);

  const formatOptions =
    presetCatalog?.formats ?? ["conversational", "deep_dive", "briefing", "debate", "critique"];
  const lengthOptions = presetCatalog?.lengths ?? ["short", "medium", "long", "longform"];
  const languageOptions =
    presetCatalog?.languages_hint ?? ["English", "Spanish", "French", "German", "Portuguese"];
  const speakerProfileOptions =
    presetCatalog?.speaker_profiles ??
    ["expert_student", "two_experts", "interviewer_guest", "debate_hosts", "storyteller_analyst"];
  const minSpeechRate = presetCatalog?.speech_rate_range.min ?? 0.8;
  const maxSpeechRate = presetCatalog?.speech_rate_range.max ?? 1.25;

  const artifactTypes = [
    { type: "summary", label: "Summary", icon: FileText, desc: "Comprehensive document summary" },
    { type: "podcast", label: "Podcast", icon: Mic, desc: "Multi-speaker audio conversation" },
    { type: "quiz", label: "Quiz", icon: FileQuestion, desc: "Test your knowledge" },
    { type: "flashcard", label: "Flashcards", icon: Layers, desc: "Spaced repetition cards" },
  ];

  const handleCreate = async (
    type: string,
    label: string,
    generationConfig?: Record<string, unknown>
  ) => {
    if (!activeNotebook) return;
    await createArtifact({
      notebook_id: activeNotebook.id,
      title: `${label} — ${activeNotebook.name}`,
      artifact_type: type,
      generation_config: generationConfig,
    });
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Content Studio</h2>
        <p className="text-sm text-muted-foreground">
          Transform your sources into learning materials
        </p>
      </div>

      {/* Generation Cards */}
      <div className="grid grid-cols-2 gap-3 mb-8">
        {artifactTypes.map(({ type, label, icon: Icon, desc }) => (
          <button
            key={type}
            onClick={() =>
              handleCreate(
                type,
                label,
                type === "podcast" ? podcastPreset : undefined
              )
            }
            className="glass-card p-5 text-left group"
          >
            <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
              <Icon className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold mb-1">{label}</h3>
            <p className="text-xs text-muted-foreground">{desc}</p>
          </button>
        ))}
      </div>

      {/* Podcast Presets */}
      <div className="glass-card p-4 mb-8">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Podcast Presets</h3>
          <span className="text-[11px] text-muted-foreground">
            {loadingPresets ? "Loading presets..." : "Loaded from API presets"}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-muted-foreground">
            Format
            <select
              value={podcastPreset.format}
              onChange={(e) => setPodcastPreset({ ...podcastPreset, format: e.target.value })}
              className="mt-1 w-full h-9 px-2 rounded-md bg-secondary/50 border border-border text-sm"
            >
              {formatOptions.map((fmt) => (
                <option key={fmt} value={fmt}>
                  {fmt.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>

          <label className="text-xs text-muted-foreground">
            Length
            <select
              value={podcastPreset.length}
              onChange={(e) => setPodcastPreset({ ...podcastPreset, length: e.target.value })}
              className="mt-1 w-full h-9 px-2 rounded-md bg-secondary/50 border border-border text-sm"
            >
              {lengthOptions.map((length) => (
                <option key={length} value={length}>
                  {length}
                </option>
              ))}
            </select>
          </label>

          <label className="text-xs text-muted-foreground">
            Language
            <select
              value={podcastPreset.language}
              onChange={(e) => setPodcastPreset({ ...podcastPreset, language: e.target.value })}
              className="mt-1 w-full h-9 px-2 rounded-md bg-secondary/50 border border-border text-sm"
            >
              {languageOptions.map((language) => (
                <option key={language} value={language}>
                  {language}
                </option>
              ))}
            </select>
          </label>

          <label className="text-xs text-muted-foreground">
            Speaker Profile
            <select
              value={podcastPreset.speaker_profile}
              onChange={(e) =>
                setPodcastPreset({ ...podcastPreset, speaker_profile: e.target.value })
              }
              className="mt-1 w-full h-9 px-2 rounded-md bg-secondary/50 border border-border text-sm"
            >
              {speakerProfileOptions.map((profile) => (
                <option key={profile} value={profile}>
                  {profile.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-3">
          <label className="text-xs text-muted-foreground flex items-center justify-between">
            <span>Speech Rate</span>
            <span className="font-mono text-foreground">{podcastPreset.speech_rate.toFixed(2)}x</span>
          </label>
          <input
            type="range"
            min={minSpeechRate}
            max={maxSpeechRate}
            step={0.05}
            value={podcastPreset.speech_rate}
            onChange={(e) =>
              setPodcastPreset({ ...podcastPreset, speech_rate: Number(e.target.value) })
            }
            className="w-full mt-1"
          />
        </div>
        <div className="mt-3">
          <button
            onClick={() => handleCreate("podcast", "Podcast", podcastPreset)}
            className="px-3 py-2 rounded-md bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all"
          >
            Generate Podcast With Preset
          </button>
        </div>
      </div>

      {/* Generated Artifacts */}
      {artifacts.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
            Generated
          </h3>
          <div className="space-y-2">
            {artifacts.map((a) => (
              <div key={a.id} className="glass-card p-4 flex items-center gap-3">
                <div
                  className={cn(
                    "w-2 h-2 rounded-full shrink-0",
                    a.status === "completed"
                      ? "bg-green-500"
                      : a.status === "processing"
                      ? "bg-yellow-500 animate-pulse"
                      : a.status === "queued"
                      ? "bg-blue-500 animate-pulse"
                      : "bg-red-500"
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{a.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {a.artifact_type} · {a.status}
                    {a.duration_seconds && ` · ${Math.round(a.duration_seconds)}s`}
                  </p>
                </div>
                {a.status === "completed" && (
                  <div className="flex gap-1 shrink-0">
                    {["pdf", "docx", "epub"].map((fmt) => (
                      <button
                        key={fmt}
                        onClick={() => useAppStore.getState().exportArtifact(a.id, fmt)}
                        className="text-[10px] px-2 py-1 rounded-md border border-border text-muted-foreground hover:text-primary hover:border-primary/30 transition-all uppercase font-semibold"
                        title={`Export as ${fmt.toUpperCase()}`}
                      >
                        <Download className="w-3 h-3 inline mr-0.5" />
                        {fmt}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// NotesPanel now imported from @/components/NotesPanel

// ── Empty State ──────────────────────────────────────────────

function EmptyState() {
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const { createNotebook, selectNotebook } = useAppStore();

  const handleCreate = async () => {
    if (!newName.trim()) return;
    const nb = await createNotebook({
      name: newName,
      description: "",
      icon: "📓",
      color: "#6366f1",
      tags: [],
    });
    selectNotebook(nb.id);
    setNewName("");
    setShowCreate(false);
  };

  return (
    <div className="flex-1 flex items-center justify-center bg-gradient-to-br from-background via-background to-primary/5">
      <div className="text-center max-w-lg px-8">
        <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary via-purple-500 to-pink-500 flex items-center justify-center mx-auto mb-6 shadow-2xl shadow-primary/30 animate-pulse-glow">
          <Brain className="w-10 h-10 text-white" />
        </div>
        <h2 className="text-3xl font-bold mb-3 gradient-text">
          Welcome to Nexus
        </h2>
        <p className="text-muted-foreground mb-8 leading-relaxed">
          Your AI-powered research companion. Upload sources, ask questions,
          and generate learning materials — all grounded in your content.
        </p>

        {showCreate ? (
          <div className="max-w-sm mx-auto animate-slide-in">
            <input
              type="text"
              placeholder="Name your notebook..."
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
              className="w-full h-12 px-4 rounded-xl bg-card border border-border text-center text-lg
                         placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30
                         focus:border-primary/50 transition-all mb-3"
            />
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                className="flex-1 h-10 rounded-xl bg-primary text-primary-foreground font-medium
                           hover:bg-primary/90 transition-all shadow-lg shadow-primary/25"
              >
                Create Notebook
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="h-10 px-4 rounded-xl border border-border hover:bg-accent transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-primary text-primary-foreground
                       font-medium text-lg shadow-2xl shadow-primary/30 hover:bg-primary/90
                       hover:-translate-y-0.5 transition-all"
          >
            <Plus className="w-5 h-5" />
            Create your first notebook
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────

export default function Home() {
  const { activeNotebook, activeTab } = useAppStore();

  return (
    <div className="h-screen flex overflow-hidden">
      <Sidebar />

      <main className="flex-1 flex flex-col overflow-hidden">
        {activeNotebook ? (
          <>
            {/* Notebook Header */}
            <div className="px-6 py-4 border-b border-border bg-card/30 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{activeNotebook.icon || "📓"}</span>
                <div>
                  <h1 className="text-lg font-semibold">{activeNotebook.name}</h1>
                  <p className="text-xs text-muted-foreground">
                    {activeNotebook.source_count} sources ·{" "}
                    {formatRelativeTime(activeNotebook.updated_at)}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-all">
                  <MoreHorizontal className="w-4 h-4" />
                </button>
              </div>
            </div>

            <TabNav />

            {activeTab === "sources" && <SourcesPanel />}
            {activeTab === "chat" && <ChatPanel />}
            {activeTab === "studio" && <StudioPanel />}
            {activeTab === "research" && <ResearchPanel />}
            {activeTab === "notes" && <NotesPanel />}
            {activeTab === "settings" && <SettingsPanel />}
          </>
        ) : (
          <EmptyState />
        )}
      </main>
    </div>
  );
}
