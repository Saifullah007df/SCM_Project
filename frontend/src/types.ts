export interface Account {
  id: string;
  username: string;
  roles: string[];
  csrf: string;
}
export interface Config {
  schema_version: number;
  profile_id: string;
  demo_heart_rate_upper_bpm: number;
  demo_spo2_lower_percent: number;
  alarm_enabled: boolean;
}
export interface Release {
  id: string;
  version: string;
  profile_id: string;
  digest: string;
  git_commit: string;
  git_path: string;
  created_at: string;
  config: Config;
  approval: {
    type?: string;
    note?: string;
    change_id?: string;
    reviewer?: string;
    approver?: string;
    external_review_verified?: boolean;
  };
}
export interface Monitor {
  id: string;
  profile_id: string;
  generation: number;
  release_id: string;
  release: Release;
  connectivity: string;
  display_state: string;
  config_state: string;
  heartbeat_age: number | null;
  disk_digest: string | null;
  last_scan: string | null;
  live_config: Config | null;
  effective: { digest?: string; payload?: Config; loaded_at?: number };
  circuit_open: boolean;
}
export interface Attempt {
  number: number;
  outcome?: string;
  error?: string;
  started_at: string;
  finished_at?: string;
}
export interface Incident {
  id: string;
  node_id: string;
  release_id: string;
  severity: string;
  reason: string;
  detected_at: string;
  recovered_at?: string;
  recovery: string;
  review: string;
  actor: string;
  provenance: string;
  diff: string;
  before: Config;
  observed_text: string;
  error?: string;
  recovery_ms?: number;
  attempts: Attempt[];
  acknowledged_by: string | null;
  task: { id: string; url: string | null; mode: string } | null;
}
export interface Change {
  id: string;
  version: string;
  author: string;
  reviewer?: string;
  approver?: string;
  config: Config;
  digest: string;
  targets: string[];
  state: string;
  created_at: string;
  base_release_id: string;
  differential_revision?: number;
  external_review_verified: boolean;
  error?: string;
}
export interface Event {
  seq: number;
  time: string;
  action: string;
  actor: string;
  node_id?: string;
  incident_id?: string;
  operation_id?: string;
  phase?: string;
  scenario?: string;
  error?: string;
  reason?: string;
  hash: string;
  previous_hash: string;
}
export interface Integration {
  mode: string;
  pending: number;
  simulated_online: boolean;
  configured: boolean;
  last_result: string;
  url: string | null;
  limitation: string;
}
export interface Overview {
  nodes: Monitor[];
  in_sync: number;
  open_incidents: number;
  integrity: boolean;
  integration: Integration;
  poll_seconds: number;
  demo: boolean;
  server_time: string;
  simulation_only: boolean;
}
export interface Snapshot {
  overview: Overview;
  incidents: Incident[];
  releases: Release[];
  changes: Change[];
  events: Event[];
}
