import { Settings, Shield, Triangle } from "lucide-react";
import type { Domain } from "@/hooks/use-fairwall";

const DOMAINS: { key: Domain; label: string }[] = [
  { key: "hiring", label: "Hiring AI" },
  { key: "lending", label: "Lending AI" },
  { key: "admissions", label: "Admissions" },
  { key: "healthcare", label: "Healthcare" },
];

interface HeaderProps {
  domain: Domain;
  onDomainChange: (d: Domain) => void;
  tenantName: string;
  trustStatus?: "HEALTHY" | "WARNING" | "CRITICAL" | null;
  onSettingsOpen: () => void;
}

export function Header({ domain, onDomainChange, tenantName, trustStatus, onSettingsOpen }: HeaderProps) {
  return (
    <header className="h-16 flex items-center px-5 gap-4 shrink-0"
      style={{
        background: "rgba(8,8,8,0.90)",
        backdropFilter: "blur(24px)",
        borderBottom: "1px solid rgba(255,140,0,0.10)",
      }}>
      {/* Logo */}
      <div className="flex items-center gap-2.5 mr-6">
        <div className="relative">
          <Shield className="w-7 h-7" style={{ color: "#FF8C00" }} />
          <Triangle className="w-2.5 h-2.5 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" style={{ color: "#FFB347", fill: "#FFB347" }} />
        </div>
        <div>
          <div className="font-bold tracking-wider" style={{ color: "#F5F5F5", fontSize: 18 }}>FairWall</div>
          <div style={{ color: "#FF8C00", fontSize: 10, letterSpacing: "0.2em" }}>AI FAIRNESS FIREWALL</div>
        </div>
      </div>

      {/* Domain tabs */}
      <nav className="flex gap-1 flex-1 justify-center">
        {DOMAINS.map(d => (
          <button key={d.key} onClick={() => onDomainChange(d.key)}
            className="px-4 py-1.5 text-sm font-medium relative transition-colors duration-200"
            style={{
              color: domain === d.key ? "#F5F5F5" : "rgba(245,245,245,0.40)",
              borderBottom: domain === d.key ? "2px solid #FF8C00" : "2px solid transparent",
              boxShadow: domain === d.key ? "0 2px 12px rgba(255,140,0,0.6)" : "none",
            }}>
            {d.label}
          </button>
        ))}
      </nav>

      {/* Right side */}
      <div className="flex items-center gap-3">
        <div className="px-3 py-1 rounded-full text-xs font-medium"
          style={{
            background: trustStatus === "CRITICAL" ? "rgba(255,23,68,0.08)" : "rgba(255,140,0,0.08)",
            border: `1px solid ${trustStatus === "CRITICAL" ? "rgba(255,23,68,0.50)" : "rgba(255,140,0,0.30)"}`,
            color: trustStatus === "CRITICAL" ? "#FF1744" : "#FFB347",
            animation: trustStatus === "CRITICAL" ? "fail-border-pulse 1.2s ease-in-out infinite" : undefined,
          }}>
          {tenantName}
        </div>
        <button onClick={onSettingsOpen}
          className="transition-transform duration-300 hover:rotate-90"
          style={{ color: "#FF8C00" }}>
          <Settings className="w-5 h-5" />
        </button>
      </div>
    </header>
  );
}
