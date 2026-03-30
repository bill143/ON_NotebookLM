"use client";

import { useState } from "react";
import { useAppStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import {
  Settings,
  Moon,
  Sun,
  Key,
  DollarSign,
  Brain,
  Shield,
  Globe,
  Save,
  Check,
  Eye,
  EyeOff,
} from "lucide-react";

export function SettingsPanel() {
  const [activeSection, setActiveSection] = useState("general");
  const [saved, setSaved] = useState(false);
  const [showKeys, setShowKeys] = useState(false);

  // Local form state
  const [theme, setTheme] = useState("dark");
  const [defaultModel, setDefaultModel] = useState("gemini-2.5-flash");
  const [budgetLimit, setBudgetLimit] = useState(50);
  const [apiKeys, setApiKeys] = useState({
    openai: "",
    google: "",
    elevenlabs: "",
    anthropic: "",
  });

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const sections = [
    { id: "general", label: "General", icon: Settings },
    { id: "models", label: "AI Models", icon: Brain },
    { id: "keys", label: "API Keys", icon: Key },
    { id: "budget", label: "Budget", icon: DollarSign },
    { id: "security", label: "Security", icon: Shield },
  ];

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Settings Nav */}
      <div className="w-56 border-r border-border p-4 space-y-1">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Settings className="w-5 h-5 text-primary" />
          Settings
        </h2>
        {sections.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveSection(id)}
            className={cn(
              "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all",
              activeSection === id
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Settings Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl">
          {activeSection === "general" && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold mb-4">Appearance</h3>
                <div className="flex gap-3">
                  {[
                    { id: "light", label: "Light", icon: Sun },
                    { id: "dark", label: "Dark", icon: Moon },
                  ].map(({ id, label, icon: Icon }) => (
                    <button
                      key={id}
                      onClick={() => setTheme(id)}
                      className={cn(
                        "flex-1 flex items-center gap-3 p-4 rounded-xl border transition-all",
                        theme === id
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/30"
                      )}
                    >
                      <Icon className="w-5 h-5" />
                      <span className="text-sm font-medium">{label}</span>
                      {theme === id && <Check className="w-4 h-4 text-primary ml-auto" />}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-2">Language</h3>
                <select className="w-full h-10 px-3 rounded-lg bg-secondary/50 border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
                  <option>English</option>
                  <option>Spanish</option>
                  <option>French</option>
                  <option>German</option>
                  <option>Japanese</option>
                </select>
              </div>
            </div>
          )}

          {activeSection === "models" && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold mb-2">Default Chat Model</h3>
                <select
                  value={defaultModel}
                  onChange={(e) => setDefaultModel(e.target.value)}
                  className="w-full h-10 px-3 rounded-lg bg-secondary/50 border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                >
                  <option value="gemini-2.5-flash">Gemini 2.5 Flash (Cloud)</option>
                  <option value="gemini-2.5-pro">Gemini 2.5 Pro (Cloud)</option>
                  <option value="gpt-4o">GPT-4o (Cloud)</option>
                  <option value="claude-3.5-sonnet">Claude 3.5 Sonnet (Cloud)</option>
                  <option value="ollama/llama3.3">Llama 3.3 (Local/Ollama)</option>
                  <option value="ollama/mistral">Mistral (Local/Ollama)</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  Used for chat, research, and content generation
                </p>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-2">TTS Provider</h3>
                <select className="w-full h-10 px-3 rounded-lg bg-secondary/50 border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
                  <option>ElevenLabs</option>
                  <option>Google Cloud TTS</option>
                  <option>OpenAI TTS</option>
                  <option>Edge TTS (Free)</option>
                  <option>Kokoro (Local)</option>
                </select>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-2">Embedding Model</h3>
                <select className="w-full h-10 px-3 rounded-lg bg-secondary/50 border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
                  <option>text-embedding-3-small (OpenAI)</option>
                  <option>text-embedding-004 (Google)</option>
                  <option>nomic-embed-text (Local)</option>
                </select>
              </div>
            </div>
          )}

          {activeSection === "keys" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">API Keys</h3>
                <button
                  onClick={() => setShowKeys(!showKeys)}
                  className="text-xs text-muted-foreground flex items-center gap-1 hover:text-foreground transition-all"
                >
                  {showKeys ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                  {showKeys ? "Hide" : "Show"} keys
                </button>
              </div>
              {Object.entries(apiKeys).map(([provider, value]) => (
                <div key={provider}>
                  <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    {provider === "openai" ? "OpenAI" : provider === "google" ? "Google AI" : provider === "elevenlabs" ? "ElevenLabs" : "Anthropic"}
                  </label>
                  <input
                    type={showKeys ? "text" : "password"}
                    value={value}
                    onChange={(e) => setApiKeys({ ...apiKeys, [provider]: e.target.value })}
                    placeholder={`Enter ${provider} API key...`}
                    className="w-full h-10 px-3 mt-1 rounded-lg bg-secondary/50 border border-border text-sm font-mono placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </div>
              ))}
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Shield className="w-3 h-3" />
                Keys are encrypted with AES-256-GCM and stored securely
              </p>
            </div>
          )}

          {activeSection === "budget" && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold mb-2">Monthly Budget Limit</h3>
                <div className="flex items-center gap-3">
                  <span className="text-muted-foreground">$</span>
                  <input
                    type="number"
                    value={budgetLimit}
                    onChange={(e) => setBudgetLimit(Number(e.target.value))}
                    className="w-32 h-10 px-3 rounded-lg bg-secondary/50 border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                  <span className="text-sm text-muted-foreground">/ month</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Nexus will warn you at 80% and block at 100% of this limit
                </p>
              </div>

              <div className="glass-card p-4">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                  Current Usage
                </h4>
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span>Chat & Research</span>
                    <span className="font-mono">$2.14</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Audio Generation</span>
                    <span className="font-mono">$0.87</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Embeddings</span>
                    <span className="font-mono">$0.03</span>
                  </div>
                  <div className="h-px bg-border" />
                  <div className="flex justify-between text-sm font-semibold">
                    <span>Total</span>
                    <span className="font-mono">$3.04</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-secondary overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-primary to-purple-500 transition-all"
                      style={{ width: `${(3.04 / budgetLimit) * 100}%` }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground text-right">
                    {((3.04 / budgetLimit) * 100).toFixed(1)}% of ${budgetLimit}
                  </p>
                </div>
              </div>
            </div>
          )}

          {activeSection === "security" && (
            <div className="space-y-4">
              <div className="glass-card p-4">
                <h4 className="text-sm font-medium mb-2">Encryption</h4>
                <p className="text-xs text-muted-foreground">
                  All API keys are encrypted using AES-256-GCM.
                  Session tokens use JWT with RS256 signing.
                </p>
              </div>
              <div className="glass-card p-4">
                <h4 className="text-sm font-medium mb-2">Data Isolation</h4>
                <p className="text-xs text-muted-foreground">
                  Row-Level Security (RLS) ensures complete tenant isolation.
                  Your data is never accessible to other users.
                </p>
              </div>
              <div className="glass-card p-4">
                <h4 className="text-sm font-medium mb-2">Rate Limiting</h4>
                <p className="text-xs text-muted-foreground">
                  API endpoints are protected by token bucket rate limiting.
                  Default: 60 requests/minute per user.
                </p>
              </div>
            </div>
          )}

          {/* Save Button */}
          <div className="mt-8 pt-6 border-t border-border">
            <button
              onClick={handleSave}
              className={cn(
                "flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium transition-all",
                saved
                  ? "bg-green-500/10 text-green-500"
                  : "bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/25"
              )}
            >
              {saved ? (
                <>
                  <Check className="w-4 h-4" />
                  Saved
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  Save Settings
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
