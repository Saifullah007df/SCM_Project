import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  ChevronRight,
  Clock,
  Database,
  FileCheck2,
  GitBranch,
  GitPullRequest,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Terminal,
  TriangleAlert,
  WifiOff,
  X,
} from "lucide-react";
import { api, ApiError } from "./api";
import type {
  Account,
  Change,
  Config,
  Event,
  Incident,
  Monitor,
  Overview,
  Release,
  Snapshot,
} from "./types";
import "./styles.css";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/dm-sans/600.css";

type Page =
  | "overview"
  | "nodes"
  | "live-demo"
  | "baselines"
  | "incidents"
  | "changes"
  | "audit"
  | "settings";
const nav = [
  ["overview", "Overview", LayoutDashboard],
  ["nodes", "Monitor nodes", Server],
  ["live-demo", "Live ICU Monitoring", Activity],
  ["baselines", "Baselines", GitBranch],
  ["incidents", "Incidents", ShieldAlert],
  ["changes", "Change control", GitPullRequest],
  ["audit", "Audit trail", History],
  ["settings", "Settings", Settings],
] as const;
const titles: Record<Page, [string, string]> = {
  overview: [
    "Every change, accounted for.",
    "Baseline integrity, recovery evidence and change governance in one place.",
  ],
  "live-demo": [
    "Live ICU configuration monitoring.",
    "Manually edit a real deployed JSON file and observe automatic baseline recovery.",
  ],
  nodes: [
    "A fleet you can inspect.",
    "Assigned releases, observed configurations and effective simulator state.",
  ],
  baselines: [
    "Approved by design.",
    "Trace each configuration to its immutable artifact and Git revision.",
  ],
  incidents: [
    "From deviation to evidence.",
    "Recovery outcomes and human review remain visible independently.",
  ],
  changes: [
    "Change with confidence.",
    "Propose an exact configuration. Review it. Approve its deployment.",
  ],
  audit: [
    "The complete sequence.",
    "A persistent record of changes, recovery steps and decisions.",
  ],
  settings: [
    "Your control plane.",
    "Integration reporting, demo controls and account management.",
  ],
};
const labels: Record<string, string> = {
  awaiting_scan: "Awaiting scan",
  in_sync: "In sync",
  recovered_verified: "Recovery verified",
  drift_detected: "Drift detected",
  intervention_required: "Intervention required",
  unknown: "State unknown",
  open: "Awaiting review",
  acknowledged: "Acknowledged",
  closed: "Closed",
  proposed: "Awaiting review",
  reviewed: "Awaiting CCB",
  approved: "Approved",
  deployed: "Deployed",
  deployment_failed: "Deployment failed",
  deploying: "Deploying",
  rejected: "Rejected",
  pending: "Pending",
};
const friendly = (s: string) => labels[s] || s.replaceAll("_", " ");
const stamp = (s?: string) =>
  s
    ? new Date(s).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "Not yet observed";
const short = (s?: string | null, n = 10) =>
  s ? s.slice(0, n) + "…" : "Unavailable";
const tone = (s: string) =>
  [
    "in_sync",
    "recovered_verified",
    "approved",
    "deployed",
    "closed",
    "online",
    "verified",
  ].includes(s)
    ? "good"
    : [
          "intervention_required",
          "drift_detected",
          "failed",
          "deployment_failed",
          "rejected",
          "SEV-1",
        ].includes(s)
      ? "bad"
      : [
            "awaiting_scan",
            "unknown",
            "offline",
            "open",
            "pending",
            "proposed",
            "reviewed",
            "acknowledged",
          ].includes(s)
        ? "warn"
        : "neutral";
function Badge({ value, label }: { value: string; label?: string }) {
  return (
    <span className={"badge " + tone(value)}>
      <span className="status-dot" />
      {label || friendly(value)}
    </span>
  );
}
function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty">
      <ShieldCheck size={28} />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
function Meta({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <span className="meta-label">{label}</span>
      <div className="meta-value">{children}</div>
    </div>
  );
}
function Panel({
  title,
  extra,
  children,
  className = "",
}: {
  title: string;
  extra?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      <header className="panel-header">
        <h2>{title}</h2>
        {extra}
      </header>
      {children}
    </section>
  );
}

function App() {
  const [account, setAccount] = useState<Account | null>(null),
    [checking, setChecking] = useState(true),
    [page, setPage] = useState<Page>("overview");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null),
    [updated, setUpdated] = useState<Date | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(""),
    [nodeId, setNodeId] = useState("ICU-Node-01"),
    [incidentId, setIncidentId] = useState<string | null>(null),
    [mobileNav, setMobileNav] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false),
    [scenario, setScenario] = useState("drift"),
    [reason, setReason] = useState("");
  const [proposalOpen, setProposalOpen] = useState(false),
    [proposalNode, setProposalNode] = useState("ICU-Node-02"),
    [version, setVersion] = useState("v1.3"),
    [upper, setUpper] = useState(125),
    [spo2, setSpo2] = useState(90),
    [enabled, setEnabled] = useState(true),
    [revision, setRevision] = useState("");
  const [query, setQuery] = useState(""),
    [auditQuery, setAuditQuery] = useState(""),
    [users, setUsers] = useState<{ username: string; roles: string[] }[]>([]);
  const [newName, setNewName] = useState(""),
    [newPassword, setNewPassword] = useState(""),
    [newRole, setNewRole] = useState("viewer");
  const fetching = useRef(false);
  const has = (...roles: string[]) =>
    !!account && roles.some((r) => account.roles.includes(r));
  const load = useCallback(async () => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      const [overview, incidents, releases, changes, audit] = await Promise.all(
        [
          api<Overview>("/overview"),
          api<Incident[]>("/incidents"),
          api<Release[]>("/releases"),
          api<Change[]>("/change-requests"),
          api<{ events: Event[] }>("/audit"),
        ],
      );
      setSnapshot({
        overview,
        incidents,
        releases,
        changes,
        events: audit.events,
      });
      setUpdated(new Date());
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setAccount(null);
        setSnapshot(null);
      } else setError(e instanceof Error ? e.message : "Unable to refresh");
    } finally {
      fetching.current = false;
    }
  }, []);
  useEffect(() => {
    api<Account>("/auth/me")
      .then(setAccount)
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);
  useEffect(() => {
    if (!account) return;
    void load();
    const timer = setInterval(() => void load(), 2000);
    return () => clearInterval(timer);
  }, [account?.id, load]);
  useEffect(() => {
    if (page === "settings" && has("admin"))
      api<{ username: string; roles: string[] }[]>("/admin/users")
        .then(setUsers)
        .catch((e) => setError(e.message));
  }, [page, account?.id]);
  async function act(task: () => Promise<unknown>, message: string) {
    setBusy(message);
    setError("");
    setNotice("");
    try {
      await task();
      setNotice(message);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy("");
    }
  }
  const mutate = <T,>(path: string, body?: unknown) =>
    api<T>(path, "POST", body, account?.csrf);
  function navigate(next: Page) {
    setPage(next);
    setMobileNav(false);
    setError("");
    setNotice("");
  }
  async function signout() {
    try {
      await mutate("/auth/logout");
    } finally {
      setAccount(null);
      setSnapshot(null);
      setNotice("");
      setPage("overview");
      setReason("");
      setDemoOpen(false);
    }
  }
  const node =
    snapshot?.overview.nodes.find((n) => n.id === nodeId) ||
    snapshot?.overview.nodes[0];
  const selectedIncident =
    snapshot?.incidents.find((i) => i.id === incidentId) ||
    snapshot?.incidents.find((i) => i.node_id === node?.id);
  const pendingChanges =
    snapshot?.changes.filter((c) =>
      ["proposed", "reviewed", "approved"].includes(c.state),
    ).length || 0;
  const captureReason = () => {
    if (reason.trim().length < 3)
      throw new Error("Enter a reason of at least three characters");
    return { reason: reason.trim() };
  };
  if (checking)
    return (
      <div className="boot">
        <ShieldCheck size={36} />
        <p>Opening AEGIS ICU…</p>
      </div>
    );
  if (!account)
    return (
      <Login
        onLogin={(u) => {
          setPage("overview");
          setAccount(u);
          setError("");
          setNotice("");
        }}
      />
    );
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (mobileNav ? "mobile-open" : "")}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("overview");
          }}
        >
          <span className="brand-icon">
            <ShieldCheck size={24} />
          </span>
          <span>
            <b>AEGIS</b>
            <small>ICU INTEGRITY</small>
          </span>
        </a>
        <div className="workspace-label">OPERATIONS WORKSPACE</div>
        <nav aria-label="Main navigation">
          {nav.map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              aria-label={label}
              className={page === id ? "active" : ""}
              onClick={() => navigate(id)}
              aria-current={page === id ? "page" : undefined}
            >
              <Icon size={18} />
              <span>{label}</span>
              {id === "changes" && pendingChanges > 0 && (
                <small className="nav-count">{pendingChanges}</small>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="sandbox-dot" />
          <b>Academic sandbox</b>
          <p>
            Three synthetic monitor processes.
            <br />
            No patient connections.
          </p>
        </div>
        <div className="account">
          <span className="avatar">
            {account.username.slice(0, 2).toUpperCase()}
          </span>
          <div>
            <b>{account.username}</b>
            <small>{account.roles.join(", ")}</small>
          </div>
          <button
            title="Sign out"
            aria-label="Sign out"
            onClick={() => void signout()}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="work-area">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Toggle navigation"
              onClick={() => setMobileNav(!mobileNav)}
            >
              <Menu size={19} />
            </button>
            <span>Operations</span>
            <ChevronRight size={13} />
            <b>{nav.find((n) => n[0] === page)?.[1]}</b>
          </div>
          <div className="topbar-right">
            <span className="environment">
              <span />
              SIMULATED ICU
            </span>
            <span className="topbar-rule" />
            <span className="role-label">{account.roles[0]}</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">CONTROL · VERIFY · RECOVER</div>
              <h1>{titles[page][0]}</h1>
              <p>{titles[page][1]}</p>
            </div>
            <div className="heading-actions">
              <button
                className="button"
                onClick={() => void load()}
                disabled={!!busy}
              >
                <RefreshCw size={15} />
                Refresh
              </button>
              {has("operator") && (
                <button
                  className="button primary"
                  onClick={() =>
                    void act(
                      () => mutate("/scan"),
                      "Scan completed — inspect node outcomes below",
                    )
                  }
                  disabled={!!busy}
                >
                  <Activity size={15} />
                  Run scan
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="banner danger" role="alert">
              <TriangleAlert size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="banner success" role="status">
              <CheckCheck size={18} />
              <span>{notice}</span>
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {busy && (
            <div className="busy" role="status">
              <RefreshCw size={14} />
              {busy.replace("completed", "in progress")}…
            </div>
          )}
          {!snapshot ? (
            <div className="empty">
              <RefreshCw size={24} />
              <h3>Loading workspace</h3>
              <p>Your operational records will appear here.</p>
            </div>
          ) : (
            <>
              {page === "overview" && (
                <>
                  <div className="metrics">
                    <Metric
                      label="NODES IN SYNC"
                      value={`${snapshot.overview.in_sync} / ${snapshot.overview.nodes.length}`}
                      detail="Fresh heartbeat + verified configuration"
                      icon={<Server size={18} />}
                      positive={snapshot.overview.in_sync === 3}
                    />
                    <Metric
                      label="INCIDENT REVIEWS"
                      value={String(snapshot.overview.open_incidents)}
                      detail="Recovery does not close an incident"
                      icon={<ShieldAlert size={18} />}
                    />
                    <Metric
                      label="REPORTING QUEUE"
                      value={String(snapshot.overview.integration.pending)}
                      detail={`${snapshot.overview.integration.mode === "real" ? "Real Phorge" : "Simulated reporting"} · durable delivery`}
                      icon={<GitBranch size={18} />}
                    />
                  </div>
                  <div className="section-heading">
                    <h2>Fleet integrity</h2>
                    <span>
                      <Clock size={13} />
                      Polling every {snapshot.overview.poll_seconds}s
                    </span>
                  </div>
                  <Fleet
                    nodes={snapshot.overview.nodes}
                    selected={nodeId}
                    onSelect={(n) => {
                      setNodeId(n.id);
                      setIncidentId(null);
                    }}
                  />
                  <div className="detail-grid">
                    <Inspection
                      node={node!}
                      incident={selectedIncident}
                      onInspect={() =>
                        navigate(selectedIncident ? "incidents" : "baselines")
                      }
                    />
                    <Evidence
                      incident={selectedIncident}
                      events={snapshot.events}
                    />
                  </div>
                  <div className="bottom-strip">
                    <div>
                      <ShieldCheck size={17} />
                      <span>
                        Audit chain{" "}
                        <b>
                          {snapshot.overview.integrity
                            ? "consistent"
                            : "requires investigation"}
                        </b>
                      </span>
                    </div>
                    <button onClick={() => navigate("audit")}>
                      Inspect audit trail
                      <ArrowRight size={14} />
                    </button>
                  </div>
                </>
              )}
              {page === "nodes" && (
                <>
                  <Fleet
                    nodes={snapshot.overview.nodes}
                    selected={nodeId}
                    onSelect={(n) => {
                      setNodeId(n.id);
                      setIncidentId(null);
                    }}
                  />
                  {node && (
                    <div className="detail-grid">
                      <Inspection
                        node={node}
                        incident={selectedIncident}
                        onInspect={() =>
                          navigate(selectedIncident ? "incidents" : "baselines")
                        }
                      />
                      <Panel
                        title="Node evidence"
                        extra={<Badge value={node.connectivity} />}
                      >
                        <div className="panel-body meta-grid">
                          <Meta label="Assigned release">
                            {node.release.version} · generation{" "}
                            {node.generation}
                          </Meta>
                          <Meta label="Latest scan">
                            {stamp(node.last_scan || undefined)}
                          </Meta>
                          <Meta label="Disk digest">
                            <code>{short(node.disk_digest, 18)}</code>
                          </Meta>
                          <Meta label="Effective digest">
                            <code>{short(node.effective.digest, 18)}</code>
                          </Meta>
                          <Meta label="Circuit breaker">
                            {node.circuit_open
                              ? "Open · intervention required"
                              : "Closed"}
                          </Meta>
                          <Meta label="Current state">
                            <Badge value={node.display_state} />
                          </Meta>
                        </div>
                      </Panel>
                    </div>
                  )}
                </>
              )}
              {page === "baselines" && (
                <>
                  <div className="section-heading">
                    <h2>Versioned release registry</h2>
                    {has("operator", "reviewer", "ccb") && (
                      <button
                        className="button primary"
                        onClick={() => {
                          setProposalOpen(true);
                          navigate("changes");
                        }}
                      >
                        <Plus size={15} />
                        Propose configuration
                      </button>
                    )}
                  </div>
                  <div className="release-grid">
                    {[...snapshot.releases].reverse().map((r) => (
                      <Panel
                        key={r.id}
                        title={r.version}
                        extra={
                          <Badge
                            value="approved"
                            label={
                              r.approval.type === "bootstrap_fixture"
                                ? "Bootstrap fixture"
                                : "CCB approved"
                            }
                          />
                        }
                      >
                        <div className="panel-body">
                          <div className="release-profile">
                            <GitBranch size={18} />
                            {r.profile_id}
                          </div>
                          <div className="meta-grid">
                            <Meta label="Git commit">
                              <code>{short(r.git_commit, 16)}</code>
                            </Meta>
                            <Meta label="Created">{stamp(r.created_at)}</Meta>
                            <Meta label="Artifact SHA-256">
                              <code>{short(r.digest, 22)}</code>
                            </Meta>
                            <Meta label="Assigned nodes">
                              {snapshot.overview.nodes
                                .filter((n) => n.release_id === r.id)
                                .map((n) => n.id.slice(-2))
                                .join(", ") || "None"}
                            </Meta>
                          </div>
                          <ConfigTable config={r.config} />
                          <div className="release-foot">
                            {r.approval.type === "bootstrap_fixture" ? (
                              <>
                                <Terminal size={14} />
                                Initial synthetic fixture
                              </>
                            ) : (
                              <>
                                <FileCheck2 size={14} />
                                {r.approval.change_id} ·{" "}
                                {r.approval.external_review_verified
                                  ? "Differential content verified"
                                  : "Local review evidence"}
                              </>
                            )}
                          </div>
                        </div>
                      </Panel>
                    ))}
                  </div>
                </>
              )}
              {page === "incidents" && (
                <>
                  <div className="section-heading">
                    <h2>
                      Incident register{" "}
                      <span className="count">{snapshot.incidents.length}</span>
                    </h2>
                    <div className="search-field">
                      <Search size={15} />
                      <input
                        aria-label="Search incidents"
                        placeholder="Search node, status or incident…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </div>
                  </div>
                  {snapshot.incidents.length === 0 ? (
                    <Panel title="Incident register">
                      <Empty
                        title="No drift recorded"
                        detail="Inject a demonstration fault or modify a live sandbox configuration to begin."
                      />
                    </Panel>
                  ) : (
                    <div className="panel table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Incident / detected</th>
                            <th>Node</th>
                            <th>Severity</th>
                            <th>Recovery</th>
                            <th>Review</th>
                          </tr>
                        </thead>
                        <tbody>
                          {snapshot.incidents
                            .filter((i) =>
                              (
                                i.node_id +
                                " " +
                                i.id +
                                " " +
                                i.recovery +
                                " " +
                                i.review
                              )
                                .toLowerCase()
                                .includes(query.toLowerCase()),
                            )
                            .map((i) => (
                              <tr
                                key={i.id}
                                className={
                                  selectedIncident?.id === i.id
                                    ? "selected"
                                    : ""
                                }
                              >
                                <td>
                                  <button
                                    className="text-link"
                                    onClick={() => {
                                      setIncidentId(i.id);
                                      setNodeId(i.node_id);
                                    }}
                                  >
                                    INC-{i.id.slice(0, 8)}
                                  </button>
                                  <small>{stamp(i.detected_at)}</small>
                                </td>
                                <td>{i.node_id}</td>
                                <td>
                                  <Badge value={i.severity} />
                                </td>
                                <td>
                                  <Badge value={i.recovery} />
                                </td>
                                <td>
                                  <Badge value={i.review} />
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {selectedIncident && (
                    <>
                      <div className="detail-grid">
                        <Inspection
                          node={
                            snapshot.overview.nodes.find(
                              (n) => n.id === selectedIncident.node_id,
                            )!
                          }
                          incident={selectedIncident}
                        />
                        <Evidence
                          incident={selectedIncident}
                          events={snapshot.events}
                        />
                      </div>
                      <Panel
                        title="Configuration difference"
                        extra={<code>{short(selectedIncident.id, 12)}</code>}
                      >
                        <div className="panel-body">
                          <pre className="diff-code">
                            {selectedIncident.diff ||
                              "No file difference: effective configuration verification failed."}
                          </pre>
                          <div className="meta-grid">
                            <Meta label="Actor / provenance">
                              {selectedIncident.actor} ·{" "}
                              {friendly(selectedIncident.provenance)}
                            </Meta>
                            <Meta label="Reporting">
                              {selectedIncident.task ? (
                                <>
                                  {selectedIncident.task.mode === "real" &&
                                  selectedIncident.task.url ? (
                                    <a
                                      href={selectedIncident.task.url}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      {selectedIncident.task.id}
                                      <ArrowUpRight size={12} />
                                    </a>
                                  ) : (
                                    <span>
                                      {selectedIncident.task.id} · simulated
                                    </span>
                                  )}
                                </>
                              ) : (
                                "Pending delivery"
                              )}
                            </Meta>
                          </div>
                          {selectedIncident.attempts.map((a) => (
                            <div className="attempt" key={a.number}>
                              <Badge value={a.outcome || "pending"} />
                              <span>
                                Attempt {a.number} · {stamp(a.started_at)}
                                {a.error ? " · " + a.error : ""}
                              </span>
                            </div>
                          ))}
                          {selectedIncident.review !== "closed" &&
                            has("operator", "reviewer", "ccb") && (
                              <div className="action-form">
                                <label htmlFor="incident-reason">
                                  Reason / resolution
                                </label>
                                <textarea
                                  id="incident-reason"
                                  value={reason}
                                  onChange={(e) => setReason(e.target.value)}
                                  placeholder="Record your acknowledgement, retry justification or closure reason…"
                                />
                                <div className="row wrap">
                                  {!selectedIncident.acknowledged_by && (
                                    <button
                                      className="button"
                                      disabled={!!busy}
                                      onClick={() =>
                                        void act(
                                          () =>
                                            mutate(
                                              "/incidents/" +
                                                selectedIncident.id +
                                                "/acknowledge",
                                              captureReason(),
                                            ),
                                          "Incident acknowledged",
                                        )
                                      }
                                    >
                                      Acknowledge
                                    </button>
                                  )}
                                  {has("operator") &&
                                    selectedIncident.recovery ===
                                      "intervention_required" && (
                                      <button
                                        className="button"
                                        disabled={!!busy}
                                        onClick={() =>
                                          void act(
                                            () =>
                                              mutate(
                                                "/incidents/" +
                                                  selectedIncident.id +
                                                  "/retry",
                                                captureReason(),
                                              ),
                                            "Recovery attempt completed — inspect its outcome",
                                          )
                                        }
                                      >
                                        Retry recovery
                                      </button>
                                    )}
                                  {has("ccb") && (
                                    <button
                                      className="button primary"
                                      disabled={
                                        !!busy ||
                                        selectedIncident.recovery !==
                                          "recovered_verified" ||
                                        !selectedIncident.acknowledged_by
                                      }
                                      onClick={() =>
                                        void act(
                                          () =>
                                            mutate(
                                              "/incidents/" +
                                                selectedIncident.id +
                                                "/close",
                                              captureReason(),
                                            ),
                                          "Incident reviewed and closed",
                                        )
                                      }
                                    >
                                      Close after review
                                    </button>
                                  )}
                                </div>
                              </div>
                            )}
                        </div>
                      </Panel>
                    </>
                  )}
                </>
              )}
              {page === "changes" && (
                <>
                  <div className="section-heading">
                    <h2>Controlled configuration changes</h2>
                    {has("operator", "reviewer", "ccb") && (
                      <button
                        className="button primary"
                        onClick={() => setProposalOpen(!proposalOpen)}
                      >
                        {proposalOpen ? <X size={15} /> : <Plus size={15} />}{" "}
                        {proposalOpen ? "Close editor" : "New proposal"}
                      </button>
                    )}
                  </div>
                  {proposalOpen && has("operator", "reviewer", "ccb") && (
                    <Panel
                      title="Propose a synthetic configuration"
                      extra={
                        <span className="muted">
                          Exact content · scoped deployment
                        </span>
                      }
                    >
                      <form
                        className="panel-body form-grid"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void act(async () => {
                            const target = snapshot.overview.nodes.find(
                              (n) => n.id === proposalNode,
                            )!;
                            const config: Config = {
                              ...target.release.config,
                              demo_heart_rate_upper_bpm: upper,
                              demo_spo2_lower_percent: spo2,
                              alarm_enabled: enabled,
                            };
                            await mutate("/change-requests", {
                              version,
                              config,
                              targets: [proposalNode],
                              differential_revision: revision
                                ? Number(revision)
                                : null,
                            });
                            setProposalOpen(false);
                          }, "Configuration proposal submitted");
                        }}
                      >
                        <label>
                          Release version
                          <input
                            required
                            value={version}
                            pattern="[a-zA-Z0-9._-]+"
                            onChange={(e) => setVersion(e.target.value)}
                          />
                        </label>
                        <label>
                          Target node
                          <select
                            value={proposalNode}
                            onChange={(e) => {
                              setProposalNode(e.target.value);
                              const r = snapshot.overview.nodes.find(
                                (n) => n.id === e.target.value,
                              )!.release.config;
                              setUpper(r.demo_heart_rate_upper_bpm);
                              setSpo2(r.demo_spo2_lower_percent);
                              setEnabled(r.alarm_enabled);
                            }}
                          >
                            {snapshot.overview.nodes.map((n) => (
                              <option key={n.id}>{n.id}</option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Synthetic upper heart-rate value
                          <input
                            type="number"
                            required
                            min={0}
                            max={300}
                            value={upper}
                            onChange={(e) => setUpper(Number(e.target.value))}
                          />
                        </label>
                        <label>
                          Synthetic lower SpO₂ value
                          <input
                            type="number"
                            required
                            min={0}
                            max={300}
                            value={spo2}
                            onChange={(e) => setSpo2(Number(e.target.value))}
                          />
                        </label>
                        <label>
                          Differential revision ID (optional)
                          <input
                            type="number"
                            min={1}
                            value={revision}
                            onChange={(e) => setRevision(e.target.value)}
                            placeholder="Real instance revision ID"
                          />
                        </label>
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(e) => setEnabled(e.target.checked)}
                          />
                          Synthetic alarm enabled
                        </label>
                        <div className="form-footer">
                          <span className="muted">
                            Demonstration fixtures. These values are not
                            clinical recommendations.
                          </span>
                          <button
                            className="button primary"
                            disabled={!!busy}
                            type="submit"
                          >
                            Submit proposal
                            <ArrowRight size={14} />
                          </button>
                        </div>
                      </form>
                    </Panel>
                  )}
                  {snapshot.changes.length === 0 ? (
                    <Panel title="Change requests">
                      <Empty
                        title="A deliberate path for every change"
                        detail="Submit a proposal, then use separate reviewer and CCB accounts to authorize it."
                      />
                    </Panel>
                  ) : (
                    snapshot.changes.map((c) => (
                      <Panel
                        key={c.id}
                        title={`${c.id} · ${c.version}`}
                        extra={<Badge value={c.state} />}
                      >
                        <div className="panel-body">
                          <div className="meta-grid four">
                            <Meta label="Submitted by">{c.author}</Meta>
                            <Meta label="Target scope">
                              {c.targets.join(", ")}
                            </Meta>
                            <Meta label="Technical reviewer">
                              {c.reviewer || "Pending"}
                            </Meta>
                            <Meta label="CCB approver">
                              {c.approver || "Pending"}
                            </Meta>
                          </div>
                          <ConfigTable
                            config={c.config}
                            previous={
                              snapshot.releases.find(
                                (r) => r.id === c.base_release_id,
                              )?.config
                            }
                          />
                          <div className="proposal-digest">
                            <span>Content digest</span>
                            <code>{short(c.digest, 24)}</code>
                            <span>
                              {c.differential_revision
                                ? `Differential D${c.differential_revision}`
                                : "Local governance mode"}
                            </span>
                          </div>
                          {c.error && (
                            <div className="inline-error">{c.error}</div>
                          )}
                          {["proposed", "reviewed", "approved"].includes(
                            c.state,
                          ) && (
                            <div className="action-form">
                              <label htmlFor={"reason-" + c.id}>
                                Decision reason
                              </label>
                              <input
                                id={"reason-" + c.id}
                                value={reason}
                                onChange={(e) => setReason(e.target.value)}
                                placeholder="Describe the review or approval decision…"
                              />
                              <div className="row wrap">
                                {c.state === "proposed" &&
                                  has("reviewer") &&
                                  c.author !== account.id && (
                                    <>
                                      <button
                                        className="button primary"
                                        disabled={!!busy}
                                        onClick={() =>
                                          void act(
                                            () =>
                                              mutate(
                                                "/change-requests/" +
                                                  c.id +
                                                  "/review",
                                                {
                                                  ...captureReason(),
                                                  digest: c.digest,
                                                  decision: "accept",
                                                },
                                              ),
                                            "Technical review accepted",
                                          )
                                        }
                                      >
                                        Accept technical review
                                      </button>
                                      <button
                                        className="button"
                                        disabled={!!busy}
                                        onClick={() =>
                                          void act(
                                            () =>
                                              mutate(
                                                "/change-requests/" +
                                                  c.id +
                                                  "/review",
                                                {
                                                  ...captureReason(),
                                                  digest: c.digest,
                                                  decision: "reject",
                                                },
                                              ),
                                            "Proposal rejected",
                                          )
                                        }
                                      >
                                        Reject
                                      </button>
                                    </>
                                  )}
                                {c.state === "reviewed" &&
                                  has("ccb") &&
                                  c.author !== account.id &&
                                  c.reviewer !== account.id && (
                                    <>
                                      <button
                                        className="button primary"
                                        disabled={!!busy}
                                        onClick={() =>
                                          void act(
                                            () =>
                                              mutate(
                                                "/change-requests/" +
                                                  c.id +
                                                  "/approve",
                                                {
                                                  ...captureReason(),
                                                  digest: c.digest,
                                                  decision: "accept",
                                                },
                                              ),
                                            "CCB authorization recorded",
                                          )
                                        }
                                      >
                                        Approve deployment
                                      </button>
                                      <button
                                        className="button"
                                        disabled={!!busy}
                                        onClick={() =>
                                          void act(
                                            () =>
                                              mutate(
                                                "/change-requests/" +
                                                  c.id +
                                                  "/approve",
                                                {
                                                  ...captureReason(),
                                                  digest: c.digest,
                                                  decision: "reject",
                                                },
                                              ),
                                            "Proposal rejected by CCB",
                                          )
                                        }
                                      >
                                        Reject
                                      </button>
                                    </>
                                  )}
                                {snapshot.overview.integration.mode ===
                                  "real" &&
                                  c.differential_revision &&
                                  has("reviewer") &&
                                  !c.external_review_verified && (
                                    <button
                                      className="button"
                                      disabled={!!busy}
                                      onClick={() =>
                                        void act(
                                          () =>
                                            mutate(
                                              "/change-requests/" +
                                                c.id +
                                                "/verify-external-review",
                                            ),
                                          "Accepted Differential content verified",
                                        )
                                      }
                                    >
                                      Verify Differential content
                                    </button>
                                  )}
                                {c.state === "approved" && has("ccb") && (
                                  <button
                                    className="button primary"
                                    disabled={
                                      !!busy ||
                                      (snapshot.overview.integration.mode ===
                                        "real" &&
                                        !c.external_review_verified)
                                    }
                                    onClick={() =>
                                      void act(
                                        () =>
                                          mutate(
                                            "/change-requests/" +
                                              c.id +
                                              "/deploy",
                                          ),
                                        "Deployment operation completed — inspect its result",
                                      )
                                    }
                                  >
                                    Deploy approved release
                                    <ArrowRight size={14} />
                                  </button>
                                )}
                                <span className="muted">
                                  {c.author === account.id
                                    ? "You cannot approve your own proposal."
                                    : c.state === "proposed"
                                      ? "A different reviewer must accept this content."
                                      : c.state === "reviewed"
                                        ? "A separate CCB approver is required."
                                        : "Authorization expires one hour after approval."}
                                </span>
                              </div>
                            </div>
                          )}
                        </div>
                      </Panel>
                    ))
                  )}
                </>
              )}
              {page === "audit" && (
                <>
                  <div className="section-heading">
                    <div className="row">
                      <h2>Persistent event ledger</h2>
                      <Badge
                        value={
                          snapshot.overview.integrity ? "verified" : "failed"
                        }
                        label={
                          snapshot.overview.integrity
                            ? "Chain consistent"
                            : "Chain invalid"
                        }
                      />
                    </div>
                    <div className="row wrap">
                      <div className="search-field">
                        <Search size={15} />
                        <input
                          aria-label="Filter audit events"
                          placeholder="Filter action, actor or node…"
                          value={auditQuery}
                          onChange={(e) => setAuditQuery(e.target.value)}
                        />
                      </div>
                      <a
                        className="button"
                        href="/api/v1/audit/export?format=json"
                        download
                      >
                        <ArrowDownToLine size={14} />
                        JSON
                      </a>
                      <a
                        className="button"
                        href="/api/v1/audit/export?format=csv"
                        download
                      >
                        CSV
                      </a>
                    </div>
                  </div>
                  <div className="panel table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Sequence / time</th>
                          <th>Event</th>
                          <th>Actor</th>
                          <th>Context</th>
                        </tr>
                      </thead>
                      <tbody>
                        {snapshot.events
                          .filter((e) =>
                            (e.action + " " + e.actor + " " + e.node_id)
                              .toLowerCase()
                              .includes(auditQuery.toLowerCase()),
                          )
                          .slice(0, 250)
                          .map((e) => (
                            <tr key={e.seq}>
                              <td>
                                #{e.seq}
                                <small>{stamp(e.time)}</small>
                              </td>
                              <td>
                                {friendly(e.action)}
                                {e.phase && <small>{friendly(e.phase)}</small>}
                              </td>
                              <td>{e.actor}</td>
                              <td>
                                {e.node_id || e.scenario || "Control plane"}
                                <small>
                                  {e.incident_id
                                    ? short(e.incident_id, 12)
                                    : short(e.hash, 14)}
                                </small>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="footnote">
                    Latest 250 matching events shown. Exports contain all
                    events. Chain consistency is tamper evidence, not protection
                    from a privileged host administrator.
                  </p>
                </>
              )}
              {page === "live-demo" && (
                <LiveDemo account={account} snapshot={snapshot} />
              )}
              {page === "settings" && (
                <>
                  <div className="detail-grid">
                    <Panel
                      title="Phorge reporting"
                      extra={
                        <Badge
                          value={
                            snapshot.overview.integration.mode === "real"
                              ? "online"
                              : "pending"
                          }
                          label={
                            snapshot.overview.integration.mode === "real"
                              ? "Real adapter configured"
                              : "Simulated adapter"
                          }
                        />
                      }
                    >
                      <div className="panel-body">
                        <div className="meta-grid">
                          <Meta label="Instance">
                            {snapshot.overview.integration.url ||
                              "No real instance configured"}
                          </Meta>
                          <Meta label="Pending reports">
                            {snapshot.overview.integration.pending}
                          </Meta>
                        </div>
                        <p className="muted">
                          {snapshot.overview.integration.last_result}
                        </p>
                        <div className="inline-note">
                          {snapshot.overview.integration.limitation}
                        </div>
                        <div className="row wrap">
                          {has("operator", "admin") && (
                            <button
                              className="button"
                              disabled={!!busy}
                              onClick={() =>
                                void act(
                                  () => mutate("/integrations/phorge/sync"),
                                  "Reporting synchronization attempted",
                                )
                              }
                            >
                              Synchronize reports
                            </button>
                          )}
                          {has("operator") && snapshot.overview.demo && (
                            <button
                              className="button"
                              disabled={!!busy}
                              onClick={() =>
                                void act(
                                  () =>
                                    mutate("/demo/reporting", {
                                      online:
                                        !snapshot.overview.integration
                                          .simulated_online,
                                    }),
                                  "Demonstration reporting availability updated",
                                )
                              }
                            >
                              {snapshot.overview.integration.simulated_online
                                ? "Simulate reporting outage"
                                : "Restore reporting"}
                            </button>
                          )}
                        </div>
                      </div>
                    </Panel>
                    <Panel title="Workspace policy">
                      <div className="panel-body meta-grid">
                        <Meta label="Environment">
                          Synthetic monitor sandbox
                        </Meta>
                        <Meta label="Polling interval">
                          {snapshot.overview.poll_seconds} seconds
                        </Meta>
                        <Meta label="Recovery retries">
                          One automatic retry
                        </Meta>
                        <Meta label="Repeated drift">
                          Circuit breaker after three recent episodes
                        </Meta>
                        <Meta label="Approval separation">
                          Submitter ≠ reviewer ≠ CCB
                        </Meta>
                        <Meta label="Integration credentials">
                          Configured on the host; never exposed here
                        </Meta>
                      </div>
                    </Panel>
                  </div>
                  {has("admin") && (
                    <Panel title="Account management">
                      <div className="panel-body">
                        <div className="table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th>Account</th>
                                <th>Role</th>
                              </tr>
                            </thead>
                            <tbody>
                              {users.map((u) => (
                                <tr key={u.username}>
                                  <td>{u.username}</td>
                                  <td>{u.roles.join(", ")}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <form
                          className="form-grid action-form"
                          onSubmit={(e) => {
                            e.preventDefault();
                            void act(async () => {
                              await mutate("/admin/users", {
                                username: newName,
                                password: newPassword,
                                role: newRole,
                              });
                              setUsers(await api("/admin/users"));
                              setNewName("");
                              setNewPassword("");
                            }, "Account created");
                          }}
                        >
                          <label>
                            Username
                            <input
                              required
                              minLength={3}
                              value={newName}
                              onChange={(e) => setNewName(e.target.value)}
                            />
                          </label>
                          <label>
                            Role
                            <select
                              value={newRole}
                              onChange={(e) => setNewRole(e.target.value)}
                            >
                              {[
                                "viewer",
                                "operator",
                                "reviewer",
                                "ccb",
                                "admin",
                              ].map((r) => (
                                <option key={r}>{r}</option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Initial password
                            <input
                              required
                              minLength={12}
                              type="password"
                              autoComplete="new-password"
                              value={newPassword}
                              onChange={(e) => setNewPassword(e.target.value)}
                            />
                          </label>
                          <div className="form-footer">
                            <span className="muted">
                              Use separate accounts for each approval
                              responsibility.
                            </span>
                            <button
                              className="button primary"
                              disabled={!!busy}
                            >
                              Create account
                            </button>
                          </div>
                        </form>
                      </div>
                    </Panel>
                  )}
                </>
              )}
              {has("operator") && snapshot.overview.demo && (
                <section className="demo-dock">
                  <button
                    className="demo-toggle"
                    onClick={() => setDemoOpen(!demoOpen)}
                    aria-expanded={demoOpen}
                  >
                    <span>
                      <SlidersHorizontal size={17} />
                      <b>Demonstration controls</b>
                      <small>Inject a controlled fault</small>
                    </span>
                    {demoOpen ? <X size={16} /> : <Plus size={16} />}
                  </button>
                  {demoOpen && (
                    <div className="demo-body">
                      <label>
                        Target node
                        <select
                          value={nodeId}
                          onChange={(e) => {
                            setNodeId(e.target.value);
                            setIncidentId(null);
                          }}
                        >
                          {snapshot.overview.nodes.map((n) => (
                            <option key={n.id}>{n.id}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Scenario
                        <select
                          value={scenario}
                          onChange={(e) => setScenario(e.target.value)}
                        >
                          {[
                            ["drift", "Unauthorized parameter edit"],
                            ["malformed", "Malformed JSON"],
                            ["missing", "Missing configuration"],
                            ["formatting", "Formatting-only change"],
                            ["reload_failure", "Simulator reload failure"],
                            ["write_failure", "Recovery write failure"],
                            ["offline", "Node offline"],
                            ["online", "Node online"],
                            ["cache_tamper", "Cached artifact tampered"],
                            [
                              "expire_authorization",
                              "Recovery authorization expired",
                            ],
                            ["clear_faults", "Clear injected fault flags"],
                            ["reset", "Reset node to assigned baseline"],
                          ].map(([v, l]) => (
                            <option key={v} value={v}>
                              {l}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        className="button primary"
                        disabled={!!busy}
                        onClick={() =>
                          void act(
                            () =>
                              mutate("/demo/scenarios", {
                                node_id: nodeId,
                                scenario,
                              }),
                            "Demonstration scenario applied — scan or wait for polling",
                          )
                        }
                      >
                        Apply scenario
                        <ArrowRight size={14} />
                      </button>
                      <p>
                        Synthetic files only. Automatic polling continues while
                        you inspect the console.
                      </p>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </main>
        <footer className="app-footer">
          <span>
            <span className="footer-dot" />
            AEGIS ICU · synthetic SCM demonstrator
          </span>
          <span>
            Last refreshed {updated ? updated.toLocaleTimeString() : "—"} ·{" "}
            {busy ? "operation in progress" : "refreshes every 2s"}
          </span>
        </footer>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  icon,
  positive = false,
}: {
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
  positive?: boolean;
}) {
  return (
    <div className="metric">
      <div className="metric-head">
        <span>{label}</span>
        <span className={positive ? "positive" : ""}>{icon}</span>
      </div>
      <div className="metric-value">{value}</div>
      <p>
        {positive && <Check size={12} />} {detail}
      </p>
    </div>
  );
}
function Fleet({
  nodes,
  selected,
  onSelect,
}: {
  nodes: Monitor[];
  selected: string;
  onSelect: (n: Monitor) => void;
}) {
  return (
    <div className="panel fleet">
      <div className="fleet-head">
        <span>MONITOR / PROFILE</span>
        <span>ASSIGNED RELEASE</span>
        <span>CONFIGURATION</span>
        <span>CONNECTIVITY</span>
        <span />
      </div>
      {nodes.map((n) => (
        <button
          key={n.id}
          className={"fleet-row " + (selected === n.id ? "selected" : "")}
          onClick={() => onSelect(n)}
          aria-pressed={selected === n.id}
        >
          <span className="node-name">
            <span
              className={
                "node-icon " + (n.connectivity === "offline" ? "offline" : "")
              }
            >
              <Server size={19} />
            </span>
            <span>
              <b>{n.id}</b>
              <small>{n.profile_id}</small>
            </span>
          </span>
          <span className="release-cell">
            <b>{n.release.version}</b>
            <small>
              <GitBranch size={11} />
              {short(n.release.git_commit, 7)}
            </small>
          </span>
          <span>
            <Badge value={n.display_state} />
          </span>
          <span className="heartbeat">
            {n.connectivity === "offline" ? (
              <>
                <WifiOff size={13} />
                Offline
              </>
            ) : (
              <>
                <span className="heartbeat-dot" />
                {n.heartbeat_age === null
                  ? "Unknown"
                  : `${n.heartbeat_age}s ago`}
              </>
            )}
          </span>
          <ChevronRight size={15} />
        </button>
      ))}
    </div>
  );
}
function Inspection({
  node,
  incident,
  onInspect,
}: {
  node: Monitor;
  incident?: Incident;
  onInspect?: () => void;
}) {
  const baseline = incident?.before || node.release.config;
  let observed: Config | null = node.live_config;
  try {
    if (incident) observed = JSON.parse(incident.observed_text);
  } catch {
    observed = null;
  }
  return (
    <Panel
      title={
        node.id +
        " · " +
        (incident ? "incident inspection" : "baseline inspection")
      }
      extra={<Badge value={incident?.severity || node.display_state} />}
    >
      <div className="panel-body">
        <div className="field-title">
          <span>Configuration parameter</span>
          <code>demo_heart_rate_upper_bpm</code>
        </div>
        <div className="comparison">
          <div>
            <small>
              {incident ? "INCIDENT BASELINE" : "ASSIGNED BASELINE"}
            </small>
            <strong>
              {baseline.demo_heart_rate_upper_bpm}
              <em>BPM</em>
            </strong>
          </div>
          <span className="compare-arrow">
            <ArrowRight size={16} />
          </span>
          <div
            className={
              observed?.demo_heart_rate_upper_bpm !==
              baseline.demo_heart_rate_upper_bpm
                ? "changed"
                : ""
            }
          >
            <small>{incident ? "OBSERVED AT INCIDENT" : "CURRENT FILE"}</small>
            <strong>
              {observed?.demo_heart_rate_upper_bpm ?? "—"}
              <em>{observed ? "BPM" : "Unavailable"}</em>
            </strong>
          </div>
        </div>
        <div
          className={
            "outcome " + tone(incident?.recovery || node.display_state)
          }
        >
          {incident?.recovery === "recovered_verified" ? (
            <ShieldCheck size={17} />
          ) : incident?.recovery === "intervention_required" ? (
            <TriangleAlert size={17} />
          ) : (
            <Activity size={17} />
          )}
          <span>
            {incident?.recovery === "recovered_verified"
              ? "File and effective simulator revision verified."
              : incident?.error ||
                (!observed
                  ? "Configuration is missing or invalid."
                  : node.connectivity === "offline"
                    ? "Current configuration cannot be confirmed remotely."
                    : "Inspect the current assigned and observed configuration.")}
          </span>
        </div>
        <div className="meta-grid">
          <Meta label="Recovery outcome">
            {incident ? <Badge value={incident.recovery} /> : "Not required"}
          </Meta>
          <Meta label="CCB review">
            {incident ? <Badge value={incident.review} /> : "No incident"}
          </Meta>
          <Meta label="Current assigned release">
            {node.release.version} · generation {node.generation}
          </Meta>
          <Meta label="Recovery duration">
            {incident?.recovery_ms !== undefined
              ? `${(incident.recovery_ms / 1000).toFixed(2)}s · measured`
              : "Not measured"}
          </Meta>
        </div>
        {onInspect && (
          <button className="button primary" onClick={onInspect}>
            {incident ? "Inspect incident" : "Inspect baseline"}
            <ArrowUpRight size={14} />
          </button>
        )}
      </div>
    </Panel>
  );
}
function Evidence({
  incident,
  events,
}: {
  incident?: Incident;
  events: Event[];
}) {
  const related = incident
    ? events
        .filter((e) => e.incident_id === incident.id)
        .sort((a, b) => a.seq - b.seq)
    : [];
  return (
    <Panel
      title="Recovery evidence"
      extra={<span className="muted">Recorded events</span>}
    >
      {!incident ? (
        <Empty
          title="No recovery required"
          detail="An incident timeline appears when a deviation is detected."
        />
      ) : (
        <div className="panel-body">
          <ol className="timeline">
            {related.slice(-8).map((e) => (
              <li
                key={e.seq}
                className={e.action.includes("failed") ? "event-failed" : ""}
              >
                <span className="timeline-point" />
                <div>
                  <b>{e.phase ? friendly(e.phase) : friendly(e.action)}</b>
                  <small>
                    {stamp(e.time)} · {e.actor}
                  </small>
                  {e.error && <p>{e.error}</p>}
                </div>
              </li>
            ))}
          </ol>
          {related.length === 0 && (
            <p className="muted">No correlated events recorded yet.</p>
          )}
          <div className="timeline-foot">
            <Clock size={13} />
            {incident.review === "closed"
              ? "CCB review complete"
              : "Human review remains " +
                friendly(incident.review).toLowerCase()}
          </div>
        </div>
      )}
    </Panel>
  );
}
function ConfigTable({
  config,
  previous,
}: {
  config: Config;
  previous?: Config;
}) {
  return (
    <div className="table-wrap config-table">
      <table>
        <thead>
          <tr>
            <th>Synthetic parameter</th>
            {previous && <th>Previous</th>}
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {[
            [
              "Upper heart-rate value",
              config.demo_heart_rate_upper_bpm,
              previous?.demo_heart_rate_upper_bpm,
            ],
            [
              "Lower SpO₂ value",
              config.demo_spo2_lower_percent,
              previous?.demo_spo2_lower_percent,
            ],
            [
              "Alarm enabled",
              String(config.alarm_enabled),
              previous ? String(previous.alarm_enabled) : undefined,
            ],
          ].map(([label, value, before]) => (
            <tr key={String(label)}>
              <td>{label}</td>
              {previous && <td className="muted">{before}</td>}
              <td
                className={previous && before !== value ? "changed-text" : ""}
              >
                {value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type LiveFile = {
  node_id: string;
  path: string;
  content: string;
  approved_digest: string;
  disk_digest: string;
};

function LiveDemo({ account, snapshot }: { account: Account; snapshot: Snapshot }) {
  const [selected, setSelected] = useState("ICU-Node-01");
  const [file, setFile] = useState<LiveFile | null>(null);
  const [editor, setEditor] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [failure, setFailure] = useState("");
  const canEdit = account.roles.includes("operator") && snapshot.overview.demo;
  const monitor = snapshot.overview.nodes.find((item) => item.id === selected);
  const incident = snapshot.incidents.find((item) => item.node_id === selected);
  const related = incident
    ? snapshot.events.filter((event) => event.incident_id === incident.id).slice(-8)
    : [];

  const readFile = useCallback(async (replaceEditor: boolean) => {
    try {
      const latest = await api<LiveFile>("/demo/live-file/" + selected);
      setFile(latest);
      if (replaceEditor) {
        setEditor(latest.content);
        setDirty(false);
      }
      setFailure("");
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "Unable to read live JSON");
    }
  }, [selected]);

  useEffect(() => {
    setFile(null);
    setEditor("");
    setDirty(false);
    setFeedback("");
    void readFile(true);
  }, [readFile]);

  useEffect(() => {
    const timer = setInterval(() => void readFile(!dirty), 2000);
    return () => clearInterval(timer);
  }, [readFile, dirty]);

  async function save() {
    if (!canEdit) return;
    try {
      JSON.parse(editor);
    } catch {
      setFailure("Invalid JSON syntax. Correct the file before saving.");
      return;
    }
    setSaving(true);
    setFailure("");
    try {
      await api("/demo/live-file/" + selected, "POST", { content: editor }, account.csrf);
      setDirty(false);
      setFeedback("Saved directly to live.json without approval. The independent agent will detect drift and restore the approved release automatically.");
      await readFile(true);
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="panel-body">
        <label htmlFor="live-demo-node">Synthetic ICU monitor</label>
        <select id="live-demo-node" value={selected} onChange={(e) => setSelected(e.target.value)}>
          {snapshot.overview.nodes.map((item) => (
            <option key={item.id} value={item.id}>{item.id}</option>
          ))}
        </select>
        <p className="muted">Two panels in this application. Agent polling: {snapshot.overview.poll_seconds}s. No manual scan required.</p>
      </div>
      {failure && <div className="banner danger" role="alert">{failure}</div>}
      {feedback && <div className="banner success" role="status">{feedback}</div>}
      <div className="detail-grid">
        <Panel title="Server — automatic drift detection and recovery" extra={monitor ? <Badge value={monitor.display_state} /> : undefined}>
          <div className="panel-body">
            <Meta label="Approved baseline">{monitor?.release.version || "Unavailable"} · {monitor?.release.config.demo_heart_rate_upper_bpm ?? "—"} BPM</Meta>
            <Meta label="Live file integrity">
              {file ? file.disk_digest === file.approved_digest ? "Matches approved baseline" : "UNAUTHORIZED DRIFT DETECTED ON DISK" : "Loading…"}
            </Meta>
            <Meta label="Effective simulator state">
              {monitor?.effective.digest === monitor?.release.digest ? "Approved baseline loaded and verified" : "Mismatch / verification pending"}
            </Meta>
            <Meta label="Agent result">{monitor ? friendly(monitor.display_state) : "Loading…"}</Meta>
            <Meta label="Last scan">{stamp(monitor?.last_scan || undefined)}</Meta>
            <Meta label="Latest incident">
              {incident ? <><b>{short(incident.id, 18)}</b> · {friendly(incident.recovery)} · {incident.recovery_ms ?? "—"} ms</> : "No incident yet"}
            </Meta>
            {incident && <p className="muted">{incident.reason} · Detected {stamp(incident.detected_at)} · Review: {friendly(incident.review)}</p>}
            <h3>Recovery timeline</h3>
            {related.length ? <ol className="timeline">{related.map((event) => (
              <li key={event.seq}><b>{friendly(event.phase || event.action)}</b><small>{stamp(event.time)} · {event.actor}</small></li>
            ))}</ol> : <p className="muted">Incident evidence appears here after the agent detects a modification.</p>}
          </div>
        </Panel>
        <Panel title="Device — manually edit the deployed JSON">
          <div className="panel-body">
            <Meta label="Actual file path"><code style={{ overflowWrap: "anywhere" }}>{file?.path || "Loading…"}</code></Meta>
            <p className="muted">Change the existing <code>demo_heart_rate_upper_bpm</code> from 120 to 160 and save. This writes to the real deployed JSON file, not an approved release.</p>
            <textarea aria-label="Editable live ICU JSON" spellCheck={false} rows={16}
              style={{ width: "100%", boxSizing: "border-box", fontFamily: "monospace", fontSize: 13 }}
              value={editor} onChange={(e) => { setEditor(e.target.value); setDirty(true); }}
              readOnly={!canEdit} />
            <div className="heading-actions">
              <button className="button primary" onClick={() => void save()} disabled={!canEdit || saving || !dirty}>
                <FileCheck2 size={16} /> {saving ? "Saving…" : "Save live.json"}
              </button>
              <button className="button" onClick={() => void readFile(true)}><RefreshCw size={15} /> Reload from disk</button>
            </div>
            {!canEdit && <p className="muted">Editing requires an Operator account and demo mode.</p>}
            <p className="muted">After recovery, Reload from disk shows the restored file. An external VS Code edit of this path works too.</p>
          </div>
        </Panel>
      </div>
      <p className="footnote">Synthetic academic demonstration only. Automatic detection and recovery are performed by the existing independent agent; this view does not call the scan or recovery endpoints.</p>
    </>
  );
}

function Login({ onLogin }: { onLogin: (u: Account) => void }) {
  const [username, setUsername] = useState("operator"),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="login-page">
      <div className="login-story">
        <a className="brand" href="#">
          <span className="brand-icon">
            <ShieldCheck size={24} />
          </span>
          <span>
            <b>AEGIS</b>
            <small>ICU INTEGRITY</small>
          </span>
        </a>
        <div className="login-story-content">
          <span className="eyebrow">CONFIGURATION INTEGRITY, MADE VISIBLE</span>
          <h1>
            Trust the baseline.
            <br />
            Verify every recovery.
          </h1>
          <p>
            A deliberate path from configuration drift to restoration, evidence
            and review.
          </p>
          <div className="login-features">
            <span>
              <ShieldCheck size={18} />
              Verified configuration recovery
            </span>
            <span>
              <GitPullRequest size={18} />
              Independent change approval
            </span>
            <span>
              <History size={18} />
              Persistent operational evidence
            </span>
          </div>
        </div>
        <span className="login-sandbox">
          <span className="sandbox-dot" />
          ACADEMIC SANDBOX · NO PATIENT CONNECTIONS
        </span>
      </div>
      <div className="login-form-wrap">
        <form
          className="login-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              onLogin(
                await api<Account>("/auth/login", "POST", {
                  username,
                  password,
                }),
              );
            } catch (e) {
              setError(e instanceof Error ? e.message : "Sign-in failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          <span className="login-shield">
            <ShieldCheck size={26} />
          </span>
          <h2>Welcome to the control room.</h2>
          <p>Sign in with your assigned workspace account.</p>
          {error && (
            <div className="banner danger" role="alert">
              {error}
            </div>
          )}
          <label htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            autoComplete="current-password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button className="button primary" disabled={busy}>
            {busy ? "Signing in…" : "Enter workspace"}
            <ArrowRight size={16} />
          </button>
          <div className="login-help">
            Your project administrator provides separate operator, reviewer and
            CCB accounts.
          </div>
          <small>AEGIS ICU · Local SCM demonstrator</small>
        </form>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
