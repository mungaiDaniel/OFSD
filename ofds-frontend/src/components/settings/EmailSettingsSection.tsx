import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Send, Loader2 } from "lucide-react";
import { settingsService } from "@/services/settingsService";
import type { EmailSettingsData, EmailQueueSettingsData } from "@/lib/types";

const CARD: React.CSSProperties = {
  background: "rgba(16, 24, 45, 0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255, 255, 255, 0.07)",
  borderRadius: "16px",
  boxShadow: "rgba(0, 0, 0, 0.25) 0px 4px 24px",
  padding: "20px 24px",
};

const LABEL: React.CSSProperties = { fontSize: "11px", color: "var(--color-text-tertiary)", marginBottom: "6px", display: "block" };
const INPUT: React.CSSProperties = {
  width: "100%",
  background: "rgba(0,0,0,0.25)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "8px",
  color: "var(--color-text-primary)",
  fontSize: "12px",
  padding: "8px 10px",
  outline: "none",
};

const SAVE_BTN = (disabled: boolean): React.CSSProperties => ({
  padding: "8px 16px",
  borderRadius: "8px",
  background: "rgb(26, 69, 255)",
  border: "none",
  color: "#fff",
  fontSize: "12px",
  fontWeight: 600,
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.6 : 1,
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
});

/**
 * Settings -> Email Sending / Email Queue. Only ever rendered for super_admin
 * (SettingsPage gates this) — these are SMTP credentials and delivery-rate
 * controls, not per-user preferences.
 */
export default function EmailSettingsSection() {
  const [email, setEmail] = useState<EmailSettingsData | null>(null);
  const [loadingEmail, setLoadingEmail] = useState(true);
  const [savingEmail, setSavingEmail] = useState(false);

  // Form fields — separate from `email` so typing doesn't fight the loaded state.
  const [server, setServer] = useState("");
  const [port, setPort] = useState("");
  const [useTls, setUseTls] = useState(true);
  const [useSsl, setUseSsl] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [defaultSender, setDefaultSender] = useState("");
  const [bcc, setBcc] = useState("");

  const [testRecipient, setTestRecipient] = useState("");
  const [sendingTest, setSendingTest] = useState(false);

  const [queue, setQueue] = useState<EmailQueueSettingsData | null>(null);
  const [loadingQueue, setLoadingQueue] = useState(true);
  const [savingQueue, setSavingQueue] = useState(false);
  const [batchSizeInput, setBatchSizeInput] = useState("");
  const [intervalInput, setIntervalInput] = useState("");

  const loadEmail = async () => {
    setLoadingEmail(true);
    try {
      const data = await settingsService.getEmailSettings();
      setEmail(data);
      if (data) {
        setServer(data.mail_server ?? "");
        setPort(data.mail_port != null ? String(data.mail_port) : "");
        setUseTls(!!data.mail_use_tls);
        setUseSsl(!!data.mail_use_ssl);
        setUsername(data.mail_username ?? "");
        setDefaultSender(data.mail_default_sender ?? "");
        setBcc(data.mail_bcc ?? "");
      }
    } catch {
      toast.error("Failed to load email settings");
    } finally {
      setLoadingEmail(false);
    }
  };

  const loadQueue = async () => {
    setLoadingQueue(true);
    try {
      const data = await settingsService.getEmailQueueSettings();
      setQueue(data);
      if (data) {
        setBatchSizeInput(String(data.batch_size));
        setIntervalInput(String(data.interval_minutes));
      }
    } catch {
      toast.error("Failed to load email queue settings");
    } finally {
      setLoadingQueue(false);
    }
  };

  useEffect(() => {
    loadEmail();
    loadQueue();
  }, []);

  const handleSaveEmail = async () => {
    setSavingEmail(true);
    try {
      const res = await settingsService.updateEmailSettings({
        mail_server: server.trim(),
        mail_port: port ? Number(port) : undefined,
        mail_use_tls: useTls,
        mail_use_ssl: useSsl,
        mail_username: username.trim(),
        ...(password.trim() ? { mail_password: password.trim() } : {}),
        mail_default_sender: defaultSender.trim(),
        mail_bcc: bcc.trim(),
      });
      if (res.status === 200) {
        toast.success("Email settings saved and applied — no restart needed");
        setPassword("");
        await loadEmail();
      } else {
        toast.error(res.message || "Failed to save");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to save email settings");
    } finally {
      setSavingEmail(false);
    }
  };

  const handleSendTest = async () => {
    if (!testRecipient.trim()) {
      toast.error("Enter a recipient email first");
      return;
    }
    setSendingTest(true);
    try {
      const res = await settingsService.sendTestEmail(testRecipient.trim());
      if (res.status === 200) {
        toast.success(res.message || "Test email sent");
      } else {
        toast.error(res.message || "Test failed");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Test email failed — check your SMTP settings");
    } finally {
      setSendingTest(false);
    }
  };

  const handleSaveQueue = async () => {
    const batchSize = Number(batchSizeInput);
    const intervalMinutes = Number(intervalInput);
    if (!batchSize || batchSize < 1 || batchSize > 1000) {
      toast.error("Batch size must be between 1 and 1000");
      return;
    }
    if (!intervalMinutes || intervalMinutes < 1 || intervalMinutes > 1440) {
      toast.error("Interval must be between 1 and 1440 minutes");
      return;
    }
    setSavingQueue(true);
    try {
      const res = await settingsService.updateEmailQueueSettings(batchSize, intervalMinutes);
      if (res.status === 200) {
        toast.success(res.message || "Email queue updated");
        await loadQueue();
      } else {
        toast.error(res.message || "Failed to save");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to save queue settings");
    } finally {
      setSavingQueue(false);
    }
  };

  const formatNextRun = (iso: string | null): string => {
    if (!iso) return "—";
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return "—";
    const mins = Math.max(0, Math.round((dt.getTime() - Date.now()) / 60000));
    return mins <= 0 ? "any moment" : `~${mins} min`;
  };

  return (
    <>
      {/* Email Sending */}
      <div style={CARD}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
          <Mail size={16} style={{ color: "rgb(96, 165, 250)" }} />
          <h3 style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>Email Sending</h3>
        </div>
        {loadingEmail ? (
          <p style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>Loading…</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <p style={{ fontSize: "11px", color: "var(--color-text-tertiary)", margin: 0 }}>
              Changes here take effect immediately — no server restart needed.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "10px" }}>
              <div>
                <label style={LABEL}>SMTP SERVER</label>
                <input style={INPUT} value={server} onChange={(e) => setServer(e.target.value)} placeholder="smtp.office365.com" />
              </div>
              <div>
                <label style={LABEL}>PORT</label>
                <input style={INPUT} type="number" value={port} onChange={(e) => setPort(e.target.value)} placeholder="587" />
              </div>
            </div>
            <div style={{ display: "flex", gap: "18px" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "var(--color-text-secondary)", cursor: "pointer" }}>
                <input type="checkbox" checked={useTls} onChange={(e) => setUseTls(e.target.checked)} /> Use TLS
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "var(--color-text-secondary)", cursor: "pointer" }}>
                <input type="checkbox" checked={useSsl} onChange={(e) => setUseSsl(e.target.checked)} /> Use SSL
              </label>
            </div>
            <div>
              <label style={LABEL}>USERNAME / LOGIN</label>
              <input style={INPUT} value={username} onChange={(e) => setUsername(e.target.value)} placeholder="mailbox@yourdomain.com" />
            </div>
            <div>
              <label style={LABEL}>PASSWORD {email?.has_password ? "(leave blank to keep current)" : ""}</label>
              <input
                style={INPUT}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={email?.has_password ? "••••••••" : "Enter password"}
              />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label style={LABEL}>FROM ADDRESS</label>
                <input style={INPUT} value={defaultSender} onChange={(e) => setDefaultSender(e.target.value)} placeholder="wealthmgt@yourdomain.com" />
              </div>
              <div>
                <label style={LABEL}>BCC (COPY EVERY EMAIL TO)</label>
                <input style={INPUT} value={bcc} onChange={(e) => setBcc(e.target.value)} placeholder="invest@yourdomain.com" />
              </div>
            </div>
            <div>
              <button onClick={handleSaveEmail} disabled={savingEmail} style={SAVE_BTN(savingEmail)}>
                {savingEmail ? <Loader2 size={13} className="spin" /> : null} Save
              </button>
            </div>

            <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "12px", marginTop: "4px" }}>
              <label style={LABEL}>SEND A TEST EMAIL TO CONFIRM THESE SETTINGS WORK</label>
              <div style={{ display: "flex", gap: "8px" }}>
                <input
                  style={{ ...INPUT, flex: 1 }}
                  value={testRecipient}
                  onChange={(e) => setTestRecipient(e.target.value)}
                  placeholder="you@example.com"
                />
                <button
                  onClick={handleSendTest}
                  disabled={sendingTest}
                  style={{ ...SAVE_BTN(sendingTest), background: "rgba(255,255,255,0.08)", flexShrink: 0 }}
                >
                  {sendingTest ? <Loader2 size={13} className="spin" /> : <Send size={13} />} Send test
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Email Queue */}
      <div style={CARD}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
          <Mail size={16} style={{ color: "rgb(96, 165, 250)" }} />
          <h3 style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>Email Queue</h3>
        </div>
        {loadingQueue ? (
          <p style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>Loading…</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <p style={{ fontSize: "11px", color: "var(--color-text-tertiary)", margin: 0 }}>
              How many approved emails go out per batch, and how often — this is the throttle that keeps large sends from tripping Office365's rate limits.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label style={LABEL}>EMAILS PER BATCH</label>
                <input style={INPUT} type="number" value={batchSizeInput} onChange={(e) => setBatchSizeInput(e.target.value)} />
              </div>
              <div>
                <label style={LABEL}>EVERY N MINUTES</label>
                <input style={INPUT} type="number" value={intervalInput} onChange={(e) => setIntervalInput(e.target.value)} />
              </div>
            </div>
            {queue && (
              <p style={{ fontSize: "11px", color: "var(--color-text-tertiary)", margin: 0 }}>
                {queue.queued_count} queued right now — next batch in {formatNextRun(queue.next_run_at)}
              </p>
            )}
            <div>
              <button onClick={handleSaveQueue} disabled={savingQueue} style={SAVE_BTN(savingQueue)}>
                {savingQueue ? <Loader2 size={13} className="spin" /> : null} Save
              </button>
            </div>
          </div>
        )}
      </div>

      <style>{`
        .spin { animation: settings-spin 0.8s linear infinite; }
        @keyframes settings-spin { to { transform: rotate(360deg); } }
      `}</style>
    </>
  );
}
