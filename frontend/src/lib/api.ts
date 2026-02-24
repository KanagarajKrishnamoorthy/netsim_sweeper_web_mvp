const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8090/api";

export type ConfigurationItem = {
  configuration_path: string;
  directory: string;
  has_metrics_xml: boolean;
  has_protocol_logs_config: boolean;
  has_plot_info: boolean;
  has_config_support: boolean;
};

export type InputCandidate = {
  parameter_id: string;
  category: string;
  label: string;
  node_path: string;
  attribute_name: string;
  current_value: string;
  value_type: string;
};

export type InputHierarchyLayer = {
  layer_key: string;
  layer_label: string;
  parameters: InputCandidate[];
};

export type InputHierarchyEntity = {
  entity_id: string;
  entity_label: string;
  entity_type: string;
  layers: InputHierarchyLayer[];
};

export type InputHierarchySection = {
  section_id: string;
  section_label: string;
  entities: InputHierarchyEntity[];
};

export type OutputCandidate = {
  metric_id: string;
  source_type: string;
  menu_name: string;
  table_name: string;
  column_name: string;
  row_key_columns: string[];
  source_file?: string;
  description?: string;
  available_now?: boolean;
};

export type SweepJob = {
  job_id: string;
  run_name?: string;
  created_at?: string;
  status: string;
  output_directory?: string;
  planned_run_count: number;
  completed_run_count: number;
  failed_run_count: number;
  cancelled_run_count: number;
  result_csv_path: string;
  warnings: string[];
  runs: Array<{
    run_index: number;
    status: string;
    duration_seconds: number | null;
    outputs: Record<string, number | string | null>;
    error_message: string | null;
  }>;
};

export type RuntimeValidation = {
  scenario_folder: { path: string; exists: boolean; valid: boolean; message: string };
  netsim_bin_path: { path: string; exists: boolean; valid: boolean; message: string };
  output_root: { path: string; exists: boolean; valid: boolean; message: string };
  all_valid: boolean;
};

export type ResultCsv = {
  headers: string[];
  rows: string[][];
  total_rows: number;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  return (await response.json()) as T;
}

export async function discoverConfigurations(scenarioFolder: string): Promise<ConfigurationItem[]> {
  const data = await req<{ items: ConfigurationItem[] }>("/discover/configurations", {
    method: "POST",
    body: JSON.stringify({ scenario_folder: scenarioFolder }),
  });
  return data.items;
}

export async function getDefaults(): Promise<{ default_output_root: string }> {
  return req<{ default_output_root: string }>("/defaults");
}

export async function selectFolder(title: string, initialPath?: string): Promise<string | null> {
  const data = await req<{ path: string | null; selected: boolean; message?: string }>("/ui/select-folder", {
    method: "POST",
    body: JSON.stringify({ title, initial_path: initialPath || null }),
  });
  return data.selected ? data.path : null;
}

export async function selectConfigurationFile(title: string, initialPath?: string): Promise<string | null> {
  const data = await req<{ path: string | null; selected: boolean; message?: string }>(
    "/ui/select-configuration",
    {
      method: "POST",
      body: JSON.stringify({ title, initial_path: initialPath || null }),
    }
  );
  return data.selected ? data.path : null;
}

export async function selectNetSimCoreFile(title: string, initialPath?: string): Promise<string | null> {
  const data = await req<{ path: string | null; selected: boolean; message?: string }>(
    "/ui/select-netsimcore",
    {
      method: "POST",
      body: JSON.stringify({ title, initial_path: initialPath || null }),
    }
  );
  return data.selected ? data.path : null;
}

export async function validateRuntimePaths(payload: {
  scenario_folder: string;
  netsim_bin_path: string;
  output_root: string | null;
}): Promise<RuntimeValidation> {
  return req<RuntimeValidation>("/validate/runtime-paths", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function discoverInputParameters(configurationPath: string): Promise<InputCandidate[]> {
  const data = await req<{ items: InputCandidate[] }>("/discover/parameters/input", {
    method: "POST",
    body: JSON.stringify({ configuration_path: configurationPath }),
  });
  return data.items;
}

export async function discoverInputHierarchy(configurationPath: string): Promise<InputHierarchySection[]> {
  const data = await req<{ sections: InputHierarchySection[] }>("/discover/parameters/input-hierarchy", {
    method: "POST",
    body: JSON.stringify({ configuration_path: configurationPath }),
  });
  return data.sections;
}

export async function discoverOutputParameters(
  configurationPath: string,
  opts?: {
    metricsPath?: string;
    generateMetricsIfMissing?: boolean;
    persistGeneratedMetrics?: boolean;
    bootstrapSession?: {
      scenario_folder: string;
      netsim_bin_path: string;
      output_root: string | null;
      license: {
        mode: "license_server" | "license_file";
        license_server: string | null;
        license_file_path: string | null;
      };
    };
  }
): Promise<{ items: OutputCandidate[]; warnings: string[]; metrics_path: string | null }> {
  const data = await req<{ items: OutputCandidate[]; warnings: string[]; metrics_path: string | null }>(
    "/discover/parameters/output",
    {
      method: "POST",
      body: JSON.stringify({
        configuration_path: configurationPath,
        metrics_path: opts?.metricsPath || null,
        generate_metrics_if_missing: !!opts?.generateMetricsIfMissing,
        persist_generated_metrics: !!opts?.persistGeneratedMetrics,
        bootstrap_session: opts?.bootstrapSession ?? null,
      }),
    }
  );
  return { items: data.items, warnings: data.warnings, metrics_path: data.metrics_path };
}

export async function createJob(payload: unknown): Promise<SweepJob> {
  return req<SweepJob>("/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listJobs(): Promise<SweepJob[]> {
  const data = await req<{ jobs: SweepJob[] }>("/jobs");
  return data.jobs;
}

export async function startJob(jobId: string): Promise<void> {
  await req(`/jobs/${jobId}/start`, { method: "POST", body: "{}" });
}

export async function cancelJob(jobId: string): Promise<void> {
  await req(`/jobs/${jobId}/cancel`, { method: "POST", body: "{}" });
}

export async function resumeJob(jobId: string): Promise<void> {
  await req(`/jobs/${jobId}/resume`, { method: "POST", body: "{}" });
}

export async function retryFailedJob(jobId: string): Promise<void> {
  await req(`/jobs/${jobId}/retry-failed`, { method: "POST", body: "{}" });
}

export async function getJob(jobId: string): Promise<SweepJob> {
  return req<SweepJob>(`/jobs/${jobId}`);
}

export async function renameJob(jobId: string, runName: string): Promise<void> {
  await req(`/jobs/${jobId}/rename`, {
    method: "POST",
    body: JSON.stringify({ run_name: runName }),
  });
}

export async function getResultCsv(jobId: string, limit = 250): Promise<ResultCsv> {
  return req<ResultCsv>(`/jobs/${jobId}/result-csv?limit=${limit}`);
}

export async function openResultCsv(jobId: string): Promise<void> {
  await req(`/jobs/${jobId}/open-result-csv`, { method: "POST", body: "{}" });
}

export async function generateValueTemplate(outputPath?: string): Promise<string> {
  const query = outputPath ? `?output_path=${encodeURIComponent(outputPath)}` : "";
  const response = await fetch(`${API_BASE}/templates/value-file${query}`);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  return response.text();
}

export function openJobEvents(jobId: string): EventSource {
  return new EventSource(`${API_BASE}/jobs/${jobId}/events`);
}

export async function sendUiHeartbeat(sessionId: string): Promise<void> {
  if (!sessionId.trim()) return;
  try {
    await req("/runtime/ui-heartbeat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch {
    // Ignore heartbeat failures; backend may not support runtime guard in dev mode.
  }
}

export async function sendUiDisconnect(sessionId: string): Promise<void> {
  if (!sessionId.trim()) return;
  try {
    await fetch(`${API_BASE}/runtime/ui-disconnect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
      keepalive: true,
    });
  } catch {
    // Ignore disconnect failures.
  }
}

export function sendUiDisconnectBeacon(sessionId: string): void {
  if (!sessionId.trim()) return;
  const payload = JSON.stringify({ session_id: sessionId });
  try {
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const blob = new Blob([payload], { type: "application/json" });
      navigator.sendBeacon(`${API_BASE}/runtime/ui-disconnect`, blob);
      return;
    }
  } catch {
    // Fall through to fetch fallback.
  }
  void sendUiDisconnect(sessionId);
}
