"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Loader2,
  Mail,
  RefreshCw,
  Send,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ZoningReportData, EmailStatusResult } from "@/lib/api";
import {
  draftOutreachEmail,
  getEmailConnectorStatus,
  sendOutreachEmail,
  type EmailDraftResult,
} from "@/lib/api";
import { fadeUp, spring, springGentle, staggerContainer, staggerItem } from "@/lib/motion";
import { DisconnectButton, EmailConfigDialog } from "./EmailConfigDialog";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OutreachPanelProps {
  report: ZoningReportData;
  sessionId: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sanitizeHtml(html: string): string {
  // Minimal sanitization — strip script/iframe tags before rendering
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi, "");
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function OutreachPanel({ report, sessionId }: OutreachPanelProps) {
  const owner = report.property_record?.owner ?? null;
  const address = report.address ?? "";

  const [status, setStatus] = useState<EmailStatusResult | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [showConfig, setShowConfig] = useState(false);

  // Draft state
  const [draft, setDraft] = useState<EmailDraftResult | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);

  // Editable draft fields
  const [toEmail, setToEmail] = useState("");
  const [toName, setToName] = useState(owner ?? "");
  const [subject, setSubject] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [showBodyPreview, setShowBodyPreview] = useState(false);

  // Send state
  const [sending, setSending] = useState(false);
  const [sentOk, setSentOk] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const isMounted = useRef(true);
  useEffect(() => () => { isMounted.current = false; }, []);

  // Load status on mount
  useEffect(() => {
    if (!sessionId) {
      setStatusLoading(false);
      return;
    }
    getEmailConnectorStatus(sessionId)
      .then((s) => { if (isMounted.current) { setStatus(s); setStatusLoading(false); } })
      .catch(() => { if (isMounted.current) setStatusLoading(false); });
  }, [sessionId]);

  const handleConnected = useCallback((s: EmailStatusResult) => {
    setStatus(s);
    setShowConfig(false);
  }, []);

  const handleDisconnected = useCallback(() => {
    setStatus({ configured: false, smtp_username: null, from_name: null, provider_hint: null, daily_sends_used: 0, daily_sends_remaining: 50 });
    setDraft(null);
  }, []);

  const handleDraft = useCallback(async () => {
    if (!sessionId || !owner) return;
    setDraftLoading(true);
    setDraftError(null);
    setDraft(null);
    setSentOk(false);
    try {
      const result = await draftOutreachEmail(
        {
          owner_name: owner,
          property_address: address,
          zoning_district: report.zoning_district ?? undefined,
          max_units: report.density_analysis?.max_units ?? undefined,
          sender_name: status?.from_name ?? undefined,
        },
        sessionId,
      );
      if (!isMounted.current) return;
      setDraft(result);
      setSubject(result.subject);
      setBodyHtml(result.body_html);
    } catch (err) {
      if (isMounted.current) setDraftError(err instanceof Error ? err.message : "Draft failed");
    } finally {
      if (isMounted.current) setDraftLoading(false);
    }
  }, [sessionId, owner, address, report, status]);

  const handleSend = useCallback(async () => {
    if (!sessionId || !toEmail || !subject || !bodyHtml) return;
    setSending(true);
    setSendError(null);
    setSentOk(false);
    try {
      await sendOutreachEmail(
        { to_email: toEmail, to_name: toName || undefined, subject, body_html: bodyHtml },
        sessionId,
      );
      if (!isMounted.current) return;
      setSentOk(true);
      // Refresh quota
      const updated = await getEmailConnectorStatus(sessionId).catch(() => null);
      if (isMounted.current && updated) setStatus(updated);
    } catch (err) {
      if (isMounted.current) setSendError(err instanceof Error ? err.message : "Send failed");
    } finally {
      if (isMounted.current) setSending(false);
    }
  }, [sessionId, toEmail, toName, subject, bodyHtml]);

  // ---------------------------------------------------------------------------
  // Render — no owner
  // ---------------------------------------------------------------------------

  if (!owner) {
    return (
      <motion.div
        className="flex flex-col items-center justify-center py-12 text-center"
        {...fadeUp}
        transition={springGentle}
      >
        <Mail className="w-10 h-10 text-[var(--text-muted)] mb-3 opacity-40" />
        <p className="text-[14px] text-[var(--text-muted)]">
          Owner information is not available for this property.
        </p>
      </motion.div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render — loading
  // ---------------------------------------------------------------------------

  if (statusLoading) {
    return (
      <div className="space-y-4 py-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 rounded-xl animate-shimmer" />
        ))}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render — not configured
  // ---------------------------------------------------------------------------

  if (!status?.configured) {
    return (
      <>
        <AnimatePresence>
          {showConfig && sessionId && (
            <EmailConfigDialog
              key="email-config"
              sessionId={sessionId}
              onConnected={handleConnected}
              onClose={() => setShowConfig(false)}
            />
          )}
        </AnimatePresence>

        <motion.div
          className="flex flex-col items-center justify-center py-10 text-center gap-4"
          {...fadeUp}
          transition={springGentle}
        >
          <div className="w-14 h-14 rounded-2xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
            <Mail className="w-7 h-7 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h3 className="text-[15px] font-semibold text-[var(--text-primary)] mb-1">
              Connect your email to reach {owner}
            </h3>
            <p className="text-[13px] text-[var(--text-muted)] max-w-xs leading-relaxed">
              PlotLot generates a personalized outreach letter and sends it through your own SMTP account. No Google account required.
            </p>
          </div>
          <motion.button
            onClick={() => setShowConfig(true)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-[14px] font-semibold"
            whileHover={{ y: -1, transition: spring }}
            whileTap={{ scale: 0.97 }}
          >
            <Mail className="w-4 h-4" />
            Connect Email
          </motion.button>
        </motion.div>
      </>
    );
  }

  // ---------------------------------------------------------------------------
  // Render — configured
  // ---------------------------------------------------------------------------

  return (
    <>
      <AnimatePresence>
        {showConfig && sessionId && (
          <EmailConfigDialog
            key="email-config"
            sessionId={sessionId}
            onConnected={handleConnected}
            onClose={() => setShowConfig(false)}
          />
        )}
      </AnimatePresence>

      <motion.div
        className="space-y-5"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {/* Connector status bar */}
        <motion.div
          variants={staggerItem}
          className="flex items-center justify-between px-4 py-3 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800/40"
        >
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
            <span className="text-[13px] text-[var(--text-primary)]">
              <span className="font-medium">{status.smtp_username}</span>
              <span className="text-[var(--text-muted)] ml-1.5">
                · {status.daily_sends_remaining} sends remaining today
              </span>
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowConfig(true)}
              className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              Settings
            </button>
            {sessionId && (
              <DisconnectButton sessionId={sessionId} onDisconnected={handleDisconnected} />
            )}
          </div>
        </motion.div>

        {/* Owner info */}
        <motion.div variants={staggerItem} className="space-y-1.5">
          <label className="text-[12px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
            Property Owner
          </label>
          <div className="px-4 py-3 rounded-xl border border-[var(--border)] bg-[var(--card-bg)]">
            <span className="text-[14px] font-medium text-[var(--text-primary)]">{owner}</span>
            <span className="text-[13px] text-[var(--text-muted)] ml-2">· {address}</span>
          </div>
        </motion.div>

        {/* To email */}
        <motion.div variants={staggerItem} className="space-y-1.5">
          <label className="text-[12px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
            Recipient Email
          </label>
          <input
            type="email"
            value={toEmail}
            onChange={(e) => setToEmail(e.target.value)}
            placeholder="owner@email.com"
            className="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-amber-500/60 transition-colors"
          />
        </motion.div>

        {/* Generate draft */}
        <motion.div variants={staggerItem}>
          <motion.button
            onClick={handleDraft}
            disabled={draftLoading}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-dashed border-amber-500/50 bg-amber-50/50 dark:bg-amber-900/10 text-amber-700 dark:text-amber-400 text-[14px] font-medium hover:border-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
            whileTap={{ scale: 0.98 }}
            transition={spring}
          >
            {draftLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : draft ? (
              <RefreshCw className="w-4 h-4" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            {draftLoading
              ? "Generating draft…"
              : draft
                ? "Regenerate with AI"
                : "Generate outreach draft with AI"}
          </motion.button>

          <AnimatePresence>
            {draftError && (
              <motion.p
                className="mt-2 text-[12px] text-red-500 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40 rounded-lg px-3 py-2"
                {...fadeUp}
                transition={spring}
              >
                {draftError}
              </motion.p>
            )}
          </AnimatePresence>
        </motion.div>

        {/* Draft editor */}
        <AnimatePresence>
          {draft && (
            <motion.div
              className="space-y-4"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={springGentle}
            >
              {/* Subject */}
              <div className="space-y-1.5">
                <label className="text-[12px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
                  Subject
                </label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] text-[14px] text-[var(--text-primary)] focus:outline-none focus:border-amber-500/60 transition-colors"
                />
              </div>

              {/* Body */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[12px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
                    Message
                  </label>
                  <button
                    onClick={() => setShowBodyPreview((v) => !v)}
                    className="flex items-center gap-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                  >
                    {showBodyPreview ? (
                      <>
                        <ChevronUp className="w-3.5 h-3.5" /> Edit
                      </>
                    ) : (
                      <>
                        <ChevronDown className="w-3.5 h-3.5" /> Preview
                      </>
                    )}
                  </button>
                </div>

                <AnimatePresence mode="wait">
                  {showBodyPreview ? (
                    <motion.div
                      key="preview"
                      className="px-4 py-3 rounded-xl border border-[var(--border)] bg-[var(--card-bg)] text-[13px] text-[var(--text-primary)] leading-relaxed prose prose-sm dark:prose-invert max-w-none"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={spring}
                      dangerouslySetInnerHTML={{ __html: sanitizeHtml(bodyHtml) }}
                    />
                  ) : (
                    <motion.textarea
                      key="editor"
                      value={bodyHtml}
                      onChange={(e) => setBodyHtml(e.target.value)}
                      rows={8}
                      className="w-full px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] text-[13px] text-[var(--text-primary)] font-mono focus:outline-none focus:border-amber-500/60 resize-y transition-colors"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={spring}
                    />
                  )}
                </AnimatePresence>
              </div>

              {/* Send row */}
              <div className="flex items-center gap-3">
                <motion.button
                  onClick={handleSend}
                  disabled={sending || !toEmail || !subject || !bodyHtml || sentOk}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-[14px] font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                  whileHover={{ y: -1, transition: spring }}
                  whileTap={{ scale: 0.97 }}
                >
                  {sending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : sentOk ? (
                    <CheckCircle className="w-4 h-4" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  {sending ? "Sending…" : sentOk ? "Sent!" : "Send Email"}
                </motion.button>

                <AnimatePresence>
                  {sentOk && (
                    <motion.span
                      className="text-[13px] text-emerald-600 dark:text-emerald-400"
                      {...fadeUp}
                      transition={spring}
                    >
                      Delivered to {toEmail}
                    </motion.span>
                  )}
                  {sendError && (
                    <motion.span
                      className="text-[13px] text-red-500"
                      {...fadeUp}
                      transition={spring}
                    >
                      {sendError}
                    </motion.span>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </>
  );
}
