import { useState } from "react";
import { useFairwall } from "@/hooks/use-fairwall";
import { Header } from "./Header";
import { TrustScoreGauge } from "./TrustScoreGauge";
import { MetricCards } from "./MetricCards";
import { SimulationButton } from "./SimulationButton";
import { TrustScoreChart } from "./TrustScoreChart";
import { InterventionFeed } from "./InterventionFeed";
import { ReviewQueue } from "./ReviewQueue";
import { SettingsModal } from "./SettingsModal";

export function FairWallDashboard() {
  const fw = useFairwall();
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="void-bg h-screen flex flex-col overflow-hidden" style={{ minWidth: 1280 }}>
      <Header
        domain={fw.domain}
        onDomainChange={fw.switchDomain}
        tenantName={fw.tenantName}
        trustStatus={fw.trustScore?.status ?? null}
        onSettingsOpen={() => setSettingsOpen(true)}
      />

      <div className="flex flex-1 gap-3 p-3 overflow-hidden">
        {/* Left column */}
        <div className="flex flex-col gap-3 shrink-0" style={{ width: 320 }}>
          <TrustScoreGauge data={fw.trustScore} />
          <MetricCards metrics={fw.metrics} />
          <SimulationButton
            isSimulating={fw.isSimulating}
            progress={fw.simulationProgress}
            total={fw.simulationTotal}
            onRun={fw.runSimulation}
          />
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-3 flex-1 overflow-hidden">
          <div style={{ height: "33%" }}>
            <TrustScoreChart data={fw.trustHistory} />
          </div>
          <div style={{ height: "34%" }}>
            <InterventionFeed events={fw.interventions} />
          </div>
          <div style={{ height: "33%" }}>
            <ReviewQueue
              items={fw.reviewQueue}
              onResolve={fw.resolveCase}
              onRunCounterfactual={fw.runCounterfactual}
              domain={fw.domain}
            />
          </div>
        </div>
      </div>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onTenantNameChange={fw.setTenantName}
      />
    </div>
  );
}
