import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function segmentColor(status) {
  if (status === "SAFE") return "#2ecc71";
  if (status === "UNSAFE_WEATHER_LOCKOUT") return "#e74c3c";
  if (status === "UNSAFE_OVERHEATING") return "#f39c12";
  if (status === "UNSAFE_CORONA_RISK") return "#8e44ad";
  if (status === "UNSAFE_LOW_INDUCTION") return "#3498db";
  return "#95a5a6";
}

function toCanvasPoint(lat, lon, bounds) {
  const width = Math.max(bounds.maxLon - bounds.minLon, 0.002);
  const height = Math.max(bounds.maxLat - bounds.minLat, 0.002);
  const x = ((lon - bounds.minLon) / width) * 88 + 6;
  const y = ((bounds.maxLat - lat) / height) * 88 + 6;
  return { x, y };
}

function gridBounds(segments, telemetry) {
  const lats = [telemetry.latitude];
  const lons = [telemetry.longitude];
  segments.forEach((entry) => {
    lats.push(entry.segment.lat_start, entry.segment.lat_end);
    lons.push(entry.segment.lon_start, entry.segment.lon_end);
  });
  const padLat = Math.max((Math.max(...lats) - Math.min(...lats)) * 0.2, 0.004);
  const padLon = Math.max((Math.max(...lons) - Math.min(...lons)) * 0.2, 0.004);
  return {
    minLat: Math.min(...lats) - padLat,
    maxLat: Math.max(...lats) + padLat,
    minLon: Math.min(...lons) - padLon,
    maxLon: Math.max(...lons) + padLon,
  };
}

export default function Dashboard() {
  const [segments, setSegments] = useState([]);
  const [telemetry, setTelemetry] = useState({
    drone_id: "DRONE-001",
    latitude: 37.7715,
    longitude: -122.4442,
    battery_percentage: 76,
    consumption_rate_per_min: 1.1,
  });
  const [recommendation, setRecommendation] = useState(null);
  const [weatherControl, setWeatherControl] = useState({
    quadrant: "NW",
    wind_speed_ms: 18,
    heavy_precipitation: false,
  });
  const [humanControl, setHumanControl] = useState({
    operator_id: "ops-01",
    force_segment_id: "",
    emergency_lockout: false,
    reason: "Routine command update",
  });
  const [message, setMessage] = useState("");
  const [maintenanceReport, setMaintenanceReport] = useState({
    alerts: [],
    highest_severity: "NORMAL",
    summary: "No predictive-maintenance data yet.",
  });

  const metrics = useMemo(() => {
    const safe = segments.filter((segment) => segment.safety_status === "SAFE").length;
    const avgField =
      segments.length === 0
        ? 0
        : segments.reduce((sum, segment) => sum + segment.magnetic_field_microtesla, 0) / segments.length;
    const watchOrWorse = segments.filter((segment) => segment.anomaly_severity && segment.anomaly_severity !== "NORMAL").length;
    return { safe, avgField, watchOrWorse };
  }, [segments]);

  async function fetchSegments() {
    const response = await fetch(`${API_BASE}/api/v1/grid/segments`);
    const payload = await response.json();
    setSegments(payload.segments || []);
  }

  async function fetchRecommendation() {
    const response = await fetch(`${API_BASE}/api/v1/routing/next-perch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(telemetry),
    });
    const payload = await response.json();
    setRecommendation(payload);
  }

  async function fetchMaintenance() {
    const response = await fetch(`${API_BASE}/api/v1/maintenance/report`);
    const payload = await response.json();
    setMaintenanceReport(payload);
  }

  async function setWeatherOverride() {
    await fetch(`${API_BASE}/api/v1/weather/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(weatherControl),
    });
    setMessage(`Weather override set for ${weatherControl.quadrant}`);
    fetchSegments();
  }

  async function setHumanOverride() {
    await fetch(`${API_BASE}/api/v1/control/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...humanControl,
        force_segment_id: humanControl.force_segment_id || null,
      }),
    });
    setMessage("Human control command applied");
    fetchRecommendation();
  }

  async function clearHumanOverride() {
    await fetch(`${API_BASE}/api/v1/control/command`, { method: "DELETE" });
    setMessage("Human control command cleared");
    fetchRecommendation();
  }

  async function sendFeedback(successfulPerch) {
    if (!recommendation || !recommendation.target_segment_id) return;
    await fetch(`${API_BASE}/api/v1/memory/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        drone_id: telemetry.drone_id,
        segment_id: recommendation.target_segment_id,
        successful_perch: successfulPerch,
        observed_charge_rate_pct_per_hr: recommendation.estimated_charge_rate_pct_per_hr || 0,
      }),
    });
    setMessage(successfulPerch ? "Success feedback recorded" : "Failure feedback recorded");
    fetchMaintenance();
  }

  useEffect(() => {
    fetchSegments();
    fetchRecommendation();
    fetchMaintenance();
    const telemetryTicker = setInterval(() => {
      setTelemetry((current) => ({
        ...current,
        latitude: current.latitude + (Math.random() - 0.5) * 0.0015,
        longitude: current.longitude + (Math.random() - 0.5) * 0.0015,
        battery_percentage: Math.max(10, current.battery_percentage - 0.2),
      }));
    }, 3000);

    const stateTicker = setInterval(() => {
      fetchSegments();
      fetchRecommendation();
      fetchMaintenance();
    }, 3500);

    return () => {
      clearInterval(telemetryTicker);
      clearInterval(stateTicker);
    };
  }, []);

  useEffect(() => {
    fetchRecommendation();
  }, [telemetry.latitude, telemetry.longitude, telemetry.battery_percentage]);

  const bounds = useMemo(() => gridBounds(segments, telemetry), [segments, telemetry]);
  const dronePoint = toCanvasPoint(telemetry.latitude, telemetry.longitude, bounds);

  return (
    <section className="dashboard-grid">
      <article className="metric-card">
        <h3>Active Drones</h3>
        <strong>1</strong>
      </article>
      <article className="metric-card">
        <h3>Grid Thermal Safety</h3>
        <strong>
          {metrics.safe}/{segments.length} safe
        </strong>
      </article>
      <article className="metric-card">
        <h3>Magnetic Induction Output</h3>
        <strong>{metrics.avgField.toFixed(2)} uT avg</strong>
      </article>
      <article className="metric-card">
        <h3>Predictive Maintenance</h3>
        <strong className={`severity-${maintenanceReport.highest_severity.toLowerCase()}`}>
          {maintenanceReport.highest_severity}
        </strong>
        <p className="status-line">{metrics.watchOrWorse} span(s) on watch</p>
      </article>

      <article className="viz-card">
        <h3>Vector Grid</h3>
        <svg viewBox="0 0 100 100" className="grid-canvas">
          {segments.map((entry) => {
            const start = toCanvasPoint(entry.segment.lat_start, entry.segment.lon_start, bounds);
            const end = toCanvasPoint(entry.segment.lat_end, entry.segment.lon_end, bounds);
            const midX = (start.x + end.x) / 2;
            const midY = (start.y + end.y) / 2;
            return (
              <g key={entry.segment.segment_id}>
                <line
                  x1={start.x}
                  y1={start.y}
                  x2={end.x}
                  y2={end.y}
                  stroke={segmentColor(entry.safety_status)}
                  strokeWidth="2.2"
                  strokeLinecap="round"
                />
                <text x={midX} y={midY - 1.6} textAnchor="middle" className="segment-label">
                  {entry.segment.segment_id}
                </text>
              </g>
            );
          })}
          <circle cx={dronePoint.x} cy={dronePoint.y} r="1.8" fill="#00d1ff" />
        </svg>
        {recommendation && (
          <p className="status-line">
            Next perch: {recommendation.target_segment_id} | Safety: {recommendation.safety_status}
          </p>
        )}
      </article>

      <article className="control-card">
        <h3>Weather Control Grid</h3>
        <label>
          Quadrant
          <select
            value={weatherControl.quadrant}
            onChange={(event) => setWeatherControl((p) => ({ ...p, quadrant: event.target.value }))}
          >
            <option value="NW">NW</option>
            <option value="NE">NE</option>
            <option value="SW">SW</option>
            <option value="SE">SE</option>
          </select>
        </label>
        <label>
          Wind Speed (m/s)
          <input
            type="number"
            value={weatherControl.wind_speed_ms}
            onChange={(event) =>
              setWeatherControl((p) => ({ ...p, wind_speed_ms: Number(event.target.value) }))
            }
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={weatherControl.heavy_precipitation}
            onChange={(event) =>
              setWeatherControl((p) => ({ ...p, heavy_precipitation: event.target.checked }))
            }
          />
          Heavy precipitation
        </label>
        <button onClick={setWeatherOverride}>Apply weather override</button>
      </article>

      <article className="control-card">
        <h3>Human Command Layer</h3>
        <label>
          Operator ID
          <input
            value={humanControl.operator_id}
            onChange={(event) => setHumanControl((p) => ({ ...p, operator_id: event.target.value }))}
          />
        </label>
        <label>
          Force Segment (optional)
          <input
            value={humanControl.force_segment_id}
            onChange={(event) => setHumanControl((p) => ({ ...p, force_segment_id: event.target.value }))}
            placeholder="SEG-C5"
          />
        </label>
        <label>
          Reason
          <input
            value={humanControl.reason}
            onChange={(event) => setHumanControl((p) => ({ ...p, reason: event.target.value }))}
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={humanControl.emergency_lockout}
            onChange={(event) => setHumanControl((p) => ({ ...p, emergency_lockout: event.target.checked }))}
          />
          Emergency grounding lockout
        </label>
        <div className="button-row">
          <button onClick={setHumanOverride}>Apply command</button>
          <button className="ghost" onClick={clearHumanOverride}>
            Clear command
          </button>
        </div>
      </article>

      <article className="control-card">
        <h3>Self-Adapting Memory Feedback</h3>
        <p>Use mission outcome feedback so this drone learns better segment preferences over time.</p>
        <div className="button-row">
          <button onClick={() => sendFeedback(true)}>Record successful perch</button>
          <button className="ghost" onClick={() => sendFeedback(false)}>
            Record failed perch
          </button>
        </div>
      </article>

      <article className="control-card maintenance-card">
        <h3>Anomaly Forecast</h3>
        <p>{maintenanceReport.summary}</p>
        <ul className="alert-list">
          {(maintenanceReport.alerts || []).slice(0, 4).map((alert) => (
            <li key={`${alert.entity_type}-${alert.entity_id}`}>
              <strong className={`severity-${alert.severity.toLowerCase()}`}>
                {alert.severity}
              </strong>{" "}
              {alert.entity_id}: {alert.predicted_issue}
            </li>
          ))}
        </ul>
      </article>

      <article className="metric-card status-card">
        <h3>System Note</h3>
        <p>{message || "Awaiting operator inputs."}</p>
      </article>
    </section>
  );
}
