import { CircleMarker, Popup, Tooltip } from "react-leaflet";
import type { Station } from "../types";
import { aqiBand, aqiColor } from "../utils/aqi";
import { fmtKm, fmtLocalTime, fmtPct, fmtPm } from "../utils/formatting";
import { AqiBadge } from "./ui";

interface Props {
  stations: Station[];
  hourly: boolean;
  selected: string | null;
  onShowSeries: (id: string) => void;
}

export default function StationMarkers({ stations, hourly, selected, onShowSeries }: Props) {
  return (
    <>
      {stations.map((s) => {
        const value = hourly ? s.value_at_time : s.mean_pm25;
        const band = aqiBand(value);
        const isSel = s.id === selected;
        return (
          <CircleMarker
            key={s.id}
            center={[s.lat, s.lon]}
            radius={isSel ? 10 : 8}
            pathOptions={{
              color: isSel ? "#eef0f3" : "#0b0d10",
              weight: isSel ? 3 : 2,
              fillColor: value == null ? "#5b616b" : aqiColor(value),
              fillOpacity: s.usable ? 1 : 0.4,
              dashArray: s.usable ? undefined : "3 3",
            }}
          >
            <Tooltip className="airscope-tip" direction="top" offset={[0, -8]}>
              <span className="font-semibold">{s.name}</span>
              <span className="text-txt-secondary"> · {value == null ? "no reading" : fmtPm(value)}{hourly ? "" : " (period mean)"}</span>
            </Tooltip>
            <Popup minWidth={240}>
              <div className="space-y-2">
                <div>
                  <div className="text-[13px] font-semibold text-txt-primary">{s.name}</div>
                  <div className="text-[11px] text-txt-muted">
                    {s.id} · {s.kind ?? "monitor"} · {s.provider}
                  </div>
                </div>
                {s.synthetic && (
                  <div className="rounded-md bg-status-warning/10 px-2 py-1 text-[11px] text-status-warning ring-1 ring-status-warning/30">
                    Simulated demo station - readings are synthetic.
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-xl font-semibold">{fmtPm(value)}</span>
                  {band && <AqiBadge category={band.short} color={band.color} textColor={band.text} />}
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px]">
                  <dt className="text-txt-muted">Latest reading</dt>
                  <dd className="text-right">{fmtPm(s.latest_pm25)}</dd>
                  <dt className="text-txt-muted">Latest time</dt>
                  <dd className="text-right">{fmtLocalTime(s.latest_timestamp)}</dd>
                  <dt className="text-txt-muted">Period mean</dt>
                  <dd className="text-right">{fmtPm(s.mean_pm25)}</dd>
                  <dt className="text-txt-muted">Data completeness</dt>
                  <dd className="text-right">{fmtPct(100 * s.completeness, 0)}</dd>
                  <dt className="text-txt-muted">Nearest other station</dt>
                  <dd className="text-right">{fmtKm(s.nearest_other_station_km)}</dd>
                  {s.loso && (
                    <>
                      <dt className="text-txt-muted">Held-out error (LOSO)</dt>
                      <dd className="text-right">RMSE {Math.round(s.loso.rmse)} vs IDW {Math.round(s.loso.rmse_idw)}</dd>
                    </>
                  )}
                </dl>
                {s.qc_flags.length > 0 && <div className="text-[11px] text-status-serious">QC: {s.qc_flags.join(", ").replace(/_/g, " ")}</div>}
                <button className="btn-ghost w-full" onClick={() => onShowSeries(s.id)}>
                  Show time series &amp; validation
                </button>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}
