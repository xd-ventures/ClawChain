import type { ServiceStatusState } from "../hooks/useServiceStatus";

interface Props {
  status: ServiceStatusState;
}

export function ServiceInfo({ status }: Props) {
  if (status.loading) return null;

  return (
    <div className="service-info">
      <span className={`service-badge ${status.acceptingNew ? "accepting" : "full"}`}>
        {status.acceptingNew ? "Accepting new bots" : "At capacity"}
      </span>
      <span className="service-slots">
        {status.activeInstances} / {status.maxInstances} slots used
      </span>
    </div>
  );
}
