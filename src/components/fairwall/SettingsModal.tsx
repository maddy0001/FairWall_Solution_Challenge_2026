import { useState, useEffect } from "react";
import { X } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
  onTenantNameChange: (name: string) => void;
}

const PRESETS = [
  { label: "Demo", key: "fw-demo-key-2026", name: "FairWall Demo" },
  { label: "Acme Corp", key: "fw-acme-corp-2026", name: "Acme Corp" },
  { label: "University", key: "fw-university-2026", name: "State University" },
];

export function SettingsModal({ open, onClose, onTenantNameChange }: Props) {
  const [apiUrl, setApiUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [tenantName, setTenantName] = useState("");

  useEffect(() => {
    if (open && typeof window !== "undefined") {
      setApiUrl(localStorage.getItem("fw_api_url") || "");
      setApiKey(localStorage.getItem("fw_api_key") || "");
      setTenantName(localStorage.getItem("fw_tenant_name") || "");
    }
  }, [open]);

  if (!open) return null;

  const save = () => {
    localStorage.setItem("fw_api_url", apiUrl);
    localStorage.setItem("fw_api_key", apiKey);
    localStorage.setItem("fw_tenant_name", tenantName);
    onTenantNameChange(tenantName || "FairWall Demo");
    onClose();
  };

  const applyPreset = (p: typeof PRESETS[number]) => {
    setApiKey(p.key);
    setTenantName(p.name);
  };

  const inputStyle = {
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.10)",
    borderRadius: 8,
    color: "#F5F5F5",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}
      style={{ background: "rgba(8,8,8,0.75)", backdropFilter: "blur(8px)" }}>
      <div className="w-[420px] p-7" onClick={e => e.stopPropagation()}
        style={{
          background: "#0F0F0F",
          border: "1px solid rgba(255,140,0,0.20)",
          borderRadius: 14,
          boxShadow: "0 24px 80px rgba(0,0,0,0.8)",
        }}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-bold text-lg" style={{ color: "#F5F5F5" }}>Dashboard Settings</h2>
          <button onClick={onClose} className="hover:text-amber-400 transition-colors" style={{ color: "rgba(245,245,245,0.30)" }}><X className="w-5 h-5" /></button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-[11px] font-medium mb-1 block tracking-wider" style={{ color: "rgba(245,245,245,0.50)" }}>BACKEND URL</label>
            <input value={apiUrl} onChange={e => setApiUrl(e.target.value)}
              placeholder="http://localhost:8000"
              className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none"
              style={{ ...inputStyle }} />
          </div>
          <div>
            <label className="text-[11px] font-medium mb-1 block tracking-wider" style={{ color: "rgba(245,245,245,0.50)" }}>API KEY</label>
            <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
              placeholder="fw-demo-key-2026"
              className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none"
              style={{ ...inputStyle }} />
          </div>
          <div>
            <label className="text-[11px] font-medium mb-1 block tracking-wider" style={{ color: "rgba(245,245,245,0.50)" }}>DISPLAY NAME</label>
            <input value={tenantName} onChange={e => setTenantName(e.target.value)}
              placeholder="FairWall Demo"
              className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none"
              style={{ ...inputStyle }} />
          </div>

          <div className="flex gap-2">
            {PRESETS.map(p => (
              <button key={p.label} onClick={() => applyPreset(p)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all"
                style={{
                  background: "transparent",
                  border: "1px solid rgba(255,140,0,0.25)",
                  color: "rgba(255,180,80,0.80)",
                }}>
                {p.label}
              </button>
            ))}
          </div>

          <button onClick={save}
            className="w-full h-10 rounded-lg font-bold text-sm"
            style={{
              background: "linear-gradient(135deg, #FF8C00, #FF5500)",
              color: "#080808",
              boxShadow: "0 4px 20px rgba(255,140,0,0.35)",
            }}>
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
}
