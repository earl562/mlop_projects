"use client";

import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle, ChevronDown, Loader2, Mail, Settings, Unplug, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  configureEmailConnector,
  disconnectEmailConnector,
  getEmailConnectorStatus,
  testEmailConnector,
  type EmailStatusResult,
} from "@/lib/api";
import { fadeUp, spring, springGentle } from "@/lib/motion";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EmailConfigDialogProps {
  sessionId: string;
  onConnected: (status: EmailStatusResult) => void;
  onClose: () => void;
}

type Provider = "gmail" | "outlook" | "yahoo" | "custom";

const PROVIDERS: { id: Provider; label: string; hint: string }[] = [
  {
    id: "gmail",
    label: "Gmail",
    hint: "Use an App Password (not your account password). Requires 2FA enabled.",
  },
  {
    id: "outlook",
    label: "Outlook / Office 365",
    hint: "Use an App Password from Microsoft account security settings.",
  },
  {
    id: "yahoo",
    label: "Yahoo Mail",
    hint: "Generate an App Password in Account Security → App passwords.",
  },
  {
    id: "custom",
    label: "Custom SMTP",
    hint: "Enter your SMTP server host and port manually.",
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EmailConfigDialog({ sessionId, onConnected, onClose }: EmailConfigDialogProps) {
  const [provider, setProvider] = useState<Provider>("gmail");
  const [providerOpen, setProviderOpen] = useState(false);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fromName, setFromName] = useState("");

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [testOk, setTestOk] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const overlayRef = useRef<HTMLDivElement>(null);

  const selectedProvider = PROVIDERS.find((p) => p.id === provider)!;

  const handleSave = useCallback(async () => {
    setError(null);
    setSaving(true);
    setSavedOk(false);
    setTestOk(false);
    try {
      await configureEmailConnector(
        {
          provider,
          smtp_host: provider === "custom" ? smtpHost : undefined,
          smtp_port: provider === "custom" ? parseInt(smtpPort, 10) : undefined,
          smtp_username: username,
          smtp_password: password,
          from_name: fromName || undefined,
        },
        sessionId,
      );
      setSavedOk(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [provider, smtpHost, smtpPort, username, password, fromName, sessionId]);

  const handleTest = useCallback(async () => {
    setError(null);
    setTesting(true);
    setTestOk(false);
    try {
      await testEmailConnector(sessionId);
      setTestOk(true);
      // Fetch updated status and close
      const status = await getEmailConnectorStatus(sessionId);
      setTimeout(() => {
        onConnected(status);
        onClose();
      }, 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  }, [sessionId, onConnected, onClose]);

  // Close on backdrop click
  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) onClose();
    },
    [onClose],
  );

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <motion.div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={springGentle}
      onClick={handleOverlayClick}
    >
      <motion.div
        className="relative w-full max-w-md bg-[var(--card-bg)] border border-[var(--border)] rounded-2xl shadow-2xl overflow-hidden"
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.97 }}
        transition={springGentle}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
              <Mail className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
                Connect Email
              </h2>
              <p className="text-[11px] text-[var(--text-muted)]">SMTP outreach connector</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--hover-bg)] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          {/* Provider picker */}
          <div className="space-y-1.5">
            <label className="text-[12px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Provider
            </label>
            <div className="relative">
              <button
                type="button"
                onClick={() => setProviderOpen((v) => !v)}
                className="w-full flex items-center justify-between px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] text-[14px] text-[var(--text-primary)] hover:border-amber-500/50 transition-colors"
              >
                <span>{selectedProvider.label}</span>
                <ChevronDown
                  className={`w-4 h-4 text-[var(--text-muted)] transition-transform ${providerOpen ? "rotate-180" : ""}`}
                />
              </button>

              <AnimatePresence>
                {providerOpen && (
                  <motion.div
                    className="absolute z-10 top-full mt-1 w-full bg-[var(--card-bg)] border border-[var(--border)] rounded-xl shadow-xl overflow-hidden"
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={spring}
                  >
                    {PROVIDERS.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => {
                          setProvider(p.id);
                          setProviderOpen(false);
                        }}
                        className={`w-full text-left px-3 py-2.5 text-[14px] hover:bg-[var(--hover-bg)] transition-colors ${
                          p.id === provider
                            ? "text-amber-600 dark:text-amber-400 font-medium"
                            : "text-[var(--text-primary)]"
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            <p className="text-[11px] text-[var(--text-muted)] leading-relaxed">
              {selectedProvider.hint}
            </p>
          </div>

          {/* Custom SMTP fields */}
          <AnimatePresence>
            {provider === "custom" && (
              <motion.div
                className="grid grid-cols-3 gap-2"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={springGentle}
              >
                <div className="col-span-2 space-y-1">
                  <label className="text-[12px] font-medium text-[var(--text-muted)]">
                    SMTP Host
                  </label>
                  <input
                    type="text"
                    value={smtpHost}
                    onChange={(e) => setSmtpHost(e.target.value)}
                    placeholder="smtp.example.com"
                    className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--input-bg)] text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-amber-500/60"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[12px] font-medium text-[var(--text-muted)]">Port</label>
                  <input
                    type="number"
                    value={smtpPort}
                    onChange={(e) => setSmtpPort(e.target.value)}
                    placeholder="587"
                    className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--input-bg)] text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-amber-500/60"
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Email + App Password */}
          <div className="space-y-1.5">
            <label className="text-[12px] font-medium text-[var(--text-muted)]">
              Email Address
            </label>
            <input
              type="email"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="you@gmail.com"
              className="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-amber-500/60 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-[12px] font-medium text-[var(--text-muted)]">App Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="xxxx xxxx xxxx xxxx"
              autoComplete="new-password"
              className="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-amber-500/60 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-[12px] font-medium text-[var(--text-muted)]">
              From Name <span className="text-[var(--text-muted)] font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={fromName}
              onChange={(e) => setFromName(e.target.value)}
              placeholder="Your Name or Company"
              className="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-amber-500/60 transition-colors"
            />
          </div>

          {/* Error */}
          <AnimatePresence>
            {error && (
              <motion.p
                className="text-[12px] text-red-500 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40 rounded-lg px-3 py-2"
                {...fadeUp}
                transition={spring}
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <motion.button
              type="button"
              onClick={handleSave}
              disabled={saving || !username || !password}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[var(--hover-bg)] border border-[var(--border)] text-[13px] font-medium text-[var(--text-primary)] disabled:opacity-50 disabled:cursor-not-allowed"
              whileTap={{ scale: 0.97 }}
              transition={spring}
            >
              {saving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : savedOk ? (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              ) : (
                <Settings className="w-4 h-4" />
              )}
              {saving ? "Saving…" : savedOk ? "Saved" : "Save"}
            </motion.button>

            <motion.button
              type="button"
              onClick={handleTest}
              disabled={testing || !savedOk}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-[13px] font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              whileTap={{ scale: 0.97 }}
              transition={spring}
            >
              {testing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : testOk ? (
                <CheckCircle className="w-4 h-4" />
              ) : (
                <Mail className="w-4 h-4" />
              )}
              {testing ? "Sending…" : testOk ? "Connected!" : "Test & Connect"}
            </motion.button>
          </div>

          <p className="text-[11px] text-[var(--text-muted)] text-center leading-relaxed">
            Credentials are encrypted at rest. PlotLot never stores your account password.
          </p>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Disconnect button (inline, used in OutreachPanel)
// ---------------------------------------------------------------------------

interface DisconnectButtonProps {
  sessionId: string;
  onDisconnected: () => void;
}

export function DisconnectButton({ sessionId, onDisconnected }: DisconnectButtonProps) {
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleDisconnect = useCallback(async () => {
    setLoading(true);
    try {
      await disconnectEmailConnector(sessionId);
      onDisconnected();
    } catch {
      // Silent — status will refresh
    } finally {
      setLoading(false);
      setConfirming(false);
    }
  }, [sessionId, onDisconnected]);

  if (confirming) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-[12px] text-[var(--text-muted)]">Remove connector?</span>
        <button
          onClick={handleDisconnect}
          disabled={loading}
          className="text-[12px] font-medium text-red-500 hover:text-red-600 transition-colors"
        >
          {loading ? "Removing…" : "Yes, remove"}
        </button>
        <button
          onClick={() => setConfirming(false)}
          className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="flex items-center gap-1.5 text-[12px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
    >
      <Unplug className="w-3.5 h-3.5" />
      Disconnect
    </button>
  );
}
