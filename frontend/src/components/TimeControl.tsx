import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Clock, Pause, Play, SkipForward } from "lucide-react";
import { useEffect, useMemo } from "react";
import { useTimesteps } from "../hooks/useAirScopeData";
import { useCityStatus } from "../hooks/useCityStatus";
import { api } from "../services/api";
import { useAppState, useDispatch } from "../state/store";
import { fmtLocalTime } from "../utils/formatting";
import { Segmented } from "./ui";

const PLAY_MS = 900;

export default function TimeControl() {
  const s = useAppState();
  const dispatch = useDispatch();
  const qc = useQueryClient();
  const { ready } = useCityStatus(s.cityId);
  const steps = useTimesteps(s.cityId, ready);
  const ts = useMemo(() => steps.data?.timestamps ?? [], [steps.data]);
  const idx = s.time ? ts.indexOf(s.time) : ts.length - 1;
  const hourly = s.timeMode === "hourly";

  // the API normalises timestamps to "+00:00"; keep the selected time in that form
  useEffect(() => {
    if (hourly && ts.length && (!s.time || ts.indexOf(s.time) < 0)) dispatch({ type: "setTime", time: ts[ts.length - 1] });
  }, [hourly, ts, s.time, dispatch]);

  // playback: advance one hour at a time and prefetch the next frame
  useEffect(() => {
    if (!s.playing || !hourly || !ts.length) return;
    const id = setInterval(() => {
      const cur = s.time ? ts.indexOf(s.time) : -1;
      const next = cur + 1 >= ts.length ? Math.max(0, ts.length - 72) : cur + 1;
      dispatch({ type: "setTime", time: ts[next] });
    }, PLAY_MS);
    return () => clearInterval(id);
  }, [s.playing, hourly, ts, s.time, dispatch]);

  useEffect(() => {
    if (!hourly || !s.cityId || idx < 0 || idx + 1 >= ts.length) return;
    const next = ts[idx + 1];
    qc.prefetchQuery({ queryKey: ["grid", s.cityId, next], queryFn: () => api.grid(s.cityId!, next), staleTime: 5 * 60_000 });
  }, [hourly, idx, ts, s.cityId, qc]);

  const step = (d: number) => {
    if (!ts.length) return;
    const n = Math.min(ts.length - 1, Math.max(0, (idx < 0 ? ts.length - 1 : idx) + d));
    dispatch({ type: "setTime", time: ts[n] });
  };

  return (
    <div className="glass flex flex-wrap items-center gap-3 rounded-xl px-3 py-2">
      <Clock className="h-4 w-4 text-brand-400" aria-hidden />
      <Segmented
        ariaLabel="Time view"
        size="sm"
        value={s.timeMode}
        onChange={(m) => dispatch({ type: "setTimeMode", mode: m, latest: steps.data?.latest })}
        options={[
          { value: "period", label: "Period average", title: "Average over the whole dataset period" },
          { value: "hourly", label: "Hourly", title: "Explore individual hours" },
        ]}
      />
      {hourly ? (
        <div className="flex min-w-[260px] flex-1 items-center gap-2">
          <button className="btn-icon h-7 w-7" onClick={() => dispatch({ type: "setPlaying", playing: !s.playing })} aria-label={s.playing ? "Pause animation" : "Play animation"}>
            {s.playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </button>
          <button className="btn-icon h-7 w-7" onClick={() => step(-1)} aria-label="Previous hour">
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <input
            type="range"
            className="range min-w-[120px] flex-1"
            min={0}
            max={Math.max(0, ts.length - 1)}
            value={Math.max(0, idx)}
            style={{ ["--fill" as string]: `${ts.length > 1 ? (100 * Math.max(0, idx)) / (ts.length - 1) : 0}%` }}
            onChange={(e) => dispatch({ type: "setTime", time: ts[Number(e.target.value)] })}
            aria-label="Select hour"
            aria-valuetext={fmtLocalTime(s.time)}
          />
          <button className="btn-icon h-7 w-7" onClick={() => step(1)} aria-label="Next hour">
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
          <button className="btn-icon h-7 w-7" onClick={() => ts.length && dispatch({ type: "setTime", time: ts[ts.length - 1] })} aria-label="Jump to latest hour">
            <SkipForward className="h-3.5 w-3.5" />
          </button>
          <span className="kbd-num min-w-[118px] text-right text-xs font-medium text-txt-primary">{fmtLocalTime(s.time)} PKT</span>
        </div>
      ) : (
        <span className="text-xs text-txt-secondary">
          {steps.data?.period?.hours ? `${steps.data.period.hours} h · ${fmtLocalTime(steps.data.period.start)} → ${fmtLocalTime(steps.data.period.end)}` : "Loading period…"}
        </span>
      )}
    </div>
  );
}
