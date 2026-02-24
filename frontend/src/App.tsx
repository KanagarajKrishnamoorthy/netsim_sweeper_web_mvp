import { useEffect, useMemo, useRef, useState } from "react";
import CombinedPlot from "./components/CombinedPlot";
import HelpTip from "./components/HelpTip";
import RunPlot from "./components/RunPlot";
import {
  InputCandidate,
  InputHierarchySection,
  OutputCandidate,
  ResultCsv,
  RuntimeValidation,
  SweepJob,
  cancelJob,
  createJob,
  discoverInputHierarchy,
  discoverInputParameters,
  discoverOutputParameters,
  generateValueTemplate,
  getDefaults,
  getJob,
  getResultCsv,
  listJobs,
  openJobEvents,
  openResultCsv,
  renameJob,
  resumeJob,
  retryFailedJob,
  selectConfigurationFile,
  selectNetSimCoreFile,
  selectFolder,
  sendUiDisconnect,
  sendUiDisconnectBeacon,
  sendUiHeartbeat,
  startJob,
  validateRuntimePaths,
} from "./lib/api";

type InputMode = "fixed" | "range" | "random" | "from_file";

type InputSpecUI = {
  selected: boolean;
  mode: InputMode;
  fixedValues: string;
  rangeStart: string;
  rangeEnd: string;
  rangeStep: string;
  randomMin: string;
  randomMax: string;
  randomCount: string;
  randomSeed: string;
  filePath: string;
  numberKind: "float" | "integer";
};

function splitCsvValues(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function isIntegerLike(text: string): boolean {
  return /^-?\d+$/.test(text.trim());
}

function defaultInputSpec(item: InputCandidate): InputSpecUI {
  const numberKind = isIntegerLike(item.current_value) ? "integer" : "float";
  return {
    selected: false,
    mode: "fixed",
    fixedValues: item.current_value,
    rangeStart: item.current_value,
    rangeEnd: item.current_value,
    rangeStep: "1",
    randomMin: item.current_value,
    randomMax: item.current_value,
    randomCount: "5",
    randomSeed: "42",
    filePath: "",
    numberKind,
  };
}

function parseNumber(text: string): number | null {
  const v = Number(text.trim());
  return Number.isFinite(v) ? v : null;
}

function parseInteger(text: string): number | null {
  const raw = text.trim();
  if (!/^-?\d+$/.test(raw)) return null;
  const value = Number(raw);
  return Number.isInteger(value) ? value : null;
}

function estimateSpecCount(spec: InputSpecUI): number {
  if (spec.mode === "fixed") {
    return Math.max(splitCsvValues(spec.fixedValues).length, 0);
  }
  if (spec.mode === "range") {
    const start = parseNumber(spec.rangeStart);
    const end = parseNumber(spec.rangeEnd);
    const step = parseNumber(spec.rangeStep);
    if (start === null || end === null || step === null || step === 0) return 0;
    if (spec.numberKind === "integer") {
      if (!Number.isInteger(start) || !Number.isInteger(end) || !Number.isInteger(step)) return 0;
    }
    const ascending = step > 0;
    if (ascending && start > end) return 0;
    if (!ascending && start < end) return 0;
    return Math.max(Math.floor((end - start) / step) + 1, 0);
  }
  if (spec.mode === "random") {
    const count = parseInteger(spec.randomCount);
    return count && count > 0 ? count : 0;
  }
  if (spec.mode === "from_file") {
    return spec.filePath.trim() ? 1 : 0;
  }
  return 0;
}

function joinPath(folder: string, fileName: string) {
  const trimmed = folder.trim().replace(/[\\/]+$/, "");
  return `${trimmed}\\${fileName}`;
}

function parentDirectory(pathText: string): string {
  const trimmed = pathText.trim().replace(/[\\/]+$/, "");
  const idx = Math.max(trimmed.lastIndexOf("\\"), trimmed.lastIndexOf("/"));
  if (idx <= 0) return "";
  return trimmed.slice(0, idx);
}

function metricLeafLabel(metricId: string): string {
  const trimmed = metricId.trim();
  if (!trimmed) return metricId;
  if (trimmed.includes("|")) {
    const parts = trimmed
      .split("|")
      .map((part) => part.trim())
      .filter(Boolean);
    return parts[parts.length - 1] || trimmed;
  }
  if (trimmed.includes("/")) {
    const parts = trimmed
      .split("/")
      .map((part) => part.trim())
      .filter(Boolean);
    return parts[parts.length - 1] || trimmed;
  }
  if (trimmed.includes(".")) {
    const parts = trimmed
      .split(".")
      .map((part) => part.trim())
      .filter(Boolean);
    const leaf = parts[parts.length - 1] || trimmed;
    return leaf.replace(/_/g, " ");
  }
  return trimmed;
}

function metricContextLabel(metricId: string): string {
  const trimmed = metricId.trim();
  if (!trimmed) return "";
  if (trimmed.includes("|")) {
    const parts = trimmed
      .split("|")
      .map((part) => part.trim())
      .filter(Boolean);
    return parts.slice(0, -1).join(" / ");
  }
  if (trimmed.includes("/")) {
    const parts = trimmed
      .split("/")
      .map((part) => part.trim())
      .filter(Boolean);
    return parts.slice(0, -1).join(" / ");
  }
  if (trimmed.includes(".")) {
    const parts = trimmed
      .split(".")
      .map((part) => part.trim())
      .filter(Boolean);
    if (parts.length > 1) {
      return parts[parts.length - 2].replace(/_/g, " ");
    }
  }
  return "";
}

function createUiSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `ui-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const STORAGE_KEYS = {
  scenarioFolder: "netsim_sweeper.scenario_folder",
  configurationPath: "netsim_sweeper.configuration_path",
  netsimBinPath: "netsim_sweeper.netsim_bin_path",
  outputRoot: "netsim_sweeper.output_root",
};

function readStoredPath(key: string): string {
  try {
    return window.localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function writeStoredPath(key: string, value: string): void {
  try {
    if (value.trim()) {
      window.localStorage.setItem(key, value.trim());
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // ignore storage failures
  }
}

function getDisplayRunName(item: SweepJob): string {
  if (item.run_name && item.run_name.trim()) {
    return item.run_name.trim();
  }
  if (item.output_directory) {
    const normalized = item.output_directory.replace(/[\\/]+$/, "");
    const parts = normalized.split(/[\\/]/);
    if (parts.length >= 2 && parts[parts.length - 2]) {
      return parts[parts.length - 2];
    }
  }
  return item.job_id;
}

function preferredEntityId(section: InputHierarchySection | null | undefined): string {
  if (!section?.entities.length) return "";
  const preferred = section.entities.find(
    (entity) => !entity.entity_label.toLowerCase().startsWith("all ")
  );
  return preferred?.entity_id ?? section.entities[0].entity_id;
}

const PLOT_COLORS = ["#0f8f9d", "#ff7a2f", "#2d5be3", "#1f9a43", "#d13b7b", "#8b5cf6", "#f59e0b"];

export default function App() {
  const [scenarioFolder, setScenarioFolder] = useState("");
  const [netsimBinPath, setNetsimBinPath] = useState("");
  const [outputRoot, setOutputRoot] = useState("");
  const [defaultOutputRoot, setDefaultOutputRoot] = useState("");
  const [selectedConfig, setSelectedConfig] = useState("");
  const [discoveredMetricsPath, setDiscoveredMetricsPath] = useState("");

  const [licenseMode, setLicenseMode] = useState<"license_server" | "license_file">("license_server");
  const [licenseServer, setLicenseServer] = useState("5053@192.168.0.4");
  const [licenseFilePath, setLicenseFilePath] = useState("");
  const [executeMode, setExecuteMode] = useState<"dry_run" | "live">("live");
  const [maxRuns, setMaxRuns] = useState(2000);
  const [autoGenerateMetrics, setAutoGenerateMetrics] = useState(true);
  const [persistGeneratedMetrics, setPersistGeneratedMetrics] = useState(false);
  const [linkCommonLabels, setLinkCommonLabels] = useState(false);

  const [runtimeValidation, setRuntimeValidation] = useState<RuntimeValidation | null>(null);
  const [inputCandidates, setInputCandidates] = useState<InputCandidate[]>([]);
  const [inputHierarchy, setInputHierarchy] = useState<InputHierarchySection[]>([]);
  const [selectedInputSectionId, setSelectedInputSectionId] = useState("");
  const [selectedInputEntityId, setSelectedInputEntityId] = useState("");
  const [selectedInputLayerKey, setSelectedInputLayerKey] = useState("__all__");
  const [outputCandidates, setOutputCandidates] = useState<OutputCandidate[]>([]);
  const [inputSpecState, setInputSpecState] = useState<Record<string, InputSpecUI>>({});
  const [selectedOutputs, setSelectedOutputs] = useState<Record<string, boolean>>({});
  const [plotSelection, setPlotSelection] = useState<Record<string, boolean>>({});
  const [plotMode, setPlotMode] = useState<"separate" | "combined">("separate");
  const [plotXAxisTitle, setPlotXAxisTitle] = useState("Iteration");
  const [plotXAxisUnit, setPlotXAxisUnit] = useState("");
  const [plotCombinedYAxisTitle, setPlotCombinedYAxisTitle] = useState("Metric Value");
  const [plotMetricUnits, setPlotMetricUnits] = useState<Record<string, string>>({});
  const [plotShowMarkers, setPlotShowMarkers] = useState(true);

  const [savedJobs, setSavedJobs] = useState<SweepJob[]>([]);
  const [job, setJob] = useState<SweepJob | null>(null);
  const [consoleLines, setConsoleLines] = useState<string[]>([]);
  const [csvPreview, setCsvPreview] = useState<ResultCsv | null>(null);

  const [inputFilter, setInputFilter] = useState("");
  const [outputFilter, setOutputFilter] = useState("");
  const [outputMenuFilter, setOutputMenuFilter] = useState("__all__");
  const [outputTableFilter, setOutputTableFilter] = useState("__all__");
  const [outputSourceFilter, setOutputSourceFilter] = useState<"__all__" | "metrics_xml" | "log_plugin">("__all__");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [pathsHydrated, setPathsHydrated] = useState(false);
  const effectiveScenarioFolder = scenarioFolder || parentDirectory(selectedConfig);

  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    void initializeDefaults();
    void refreshSavedRuns();
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    const uiSessionId = createUiSessionId();
    void sendUiHeartbeat(uiSessionId);
    const heartbeatTimer = window.setInterval(() => {
      void sendUiHeartbeat(uiSessionId);
    }, 8000);
    const onBeforeUnload = () => {
      sendUiDisconnectBeacon(uiSessionId);
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.clearInterval(heartbeatTimer);
      void sendUiDisconnect(uiSessionId);
    };
  }, []);

  useEffect(() => {
    if (!pathsHydrated) return;
    writeStoredPath(STORAGE_KEYS.scenarioFolder, scenarioFolder);
  }, [scenarioFolder, pathsHydrated]);

  useEffect(() => {
    if (!pathsHydrated) return;
    writeStoredPath(STORAGE_KEYS.configurationPath, selectedConfig);
  }, [selectedConfig, pathsHydrated]);

  useEffect(() => {
    if (!pathsHydrated) return;
    writeStoredPath(STORAGE_KEYS.netsimBinPath, netsimBinPath);
  }, [netsimBinPath, pathsHydrated]);

  useEffect(() => {
    if (!pathsHydrated) return;
    writeStoredPath(STORAGE_KEYS.outputRoot, outputRoot);
  }, [outputRoot, pathsHydrated]);

  async function initializeDefaults() {
    const rememberedScenarioFolder = readStoredPath(STORAGE_KEYS.scenarioFolder);
    const rememberedConfigPath = readStoredPath(STORAGE_KEYS.configurationPath);
    const rememberedNetsimBin = readStoredPath(STORAGE_KEYS.netsimBinPath);
    const rememberedOutputRoot = readStoredPath(STORAGE_KEYS.outputRoot);

    if (rememberedScenarioFolder) {
      setScenarioFolder(rememberedScenarioFolder);
    }
    if (rememberedConfigPath) {
      setSelectedConfig(rememberedConfigPath);
      if (!rememberedScenarioFolder) {
        const inferred = parentDirectory(rememberedConfigPath);
        if (inferred) {
          setScenarioFolder(inferred);
        }
      }
    } else if (rememberedScenarioFolder) {
      setSelectedConfig(joinPath(rememberedScenarioFolder, "Configuration.netsim"));
    }
    if (rememberedNetsimBin) {
      setNetsimBinPath(rememberedNetsimBin);
    }
    if (rememberedOutputRoot) {
      setOutputRoot(rememberedOutputRoot);
    }
    try {
      const defaults = await getDefaults();
      setDefaultOutputRoot(defaults.default_output_root);
      if (!rememberedOutputRoot) {
        setOutputRoot(defaults.default_output_root);
      }
    } catch {
      // No-op: manual entry still possible.
    } finally {
      setPathsHydrated(true);
    }
  }

  async function refreshSavedRuns() {
    try {
      const jobs = await listJobs();
      jobs.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || "")).reverse();
      setSavedJobs(jobs);
    } catch {
      // No-op
    }
  }

  function subscribeToJob(jobId: string) {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    const events = openJobEvents(jobId);
    eventSourceRef.current = events;
    events.onmessage = async (evt) => {
      try {
        const payload = JSON.parse(evt.data) as { event: string; run_index?: number; line?: string };
        if (payload.event === "run_console" && payload.line) {
          setConsoleLines((prev) => [...prev.slice(-500), `[run ${payload.run_index ?? "-"}] ${payload.line}`]);
          return;
        }
      } catch {
        // fall through to refresh
      }
      const latest = await getJob(jobId);
      setJob(latest);
      if (["completed", "failed", "cancelled"].includes(latest.status)) {
        await refreshSavedRuns();
      }
    };
    events.onerror = () => {
      events.close();
      if (eventSourceRef.current === events) {
        eventSourceRef.current = null;
      }
    };
  }

  async function browseScenarioFolder() {
    const selected = await selectConfigurationFile(
      "Select Configuration.netsim",
      selectedConfig || scenarioFolder || undefined
    );
    if (selected) {
      setSelectedConfig(selected);
      const folder = parentDirectory(selected);
      if (folder) {
        setScenarioFolder(folder);
      }
      setDiscoveredMetricsPath("");
    }
  }

  async function browseNetsimBin() {
    const selected = await selectNetSimCoreFile(
      "Select NetSimCore.exe",
      netsimBinPath || effectiveScenarioFolder || undefined
    );
    if (selected) {
      setNetsimBinPath(selected);
    }
  }

  async function browseOutputRoot() {
    const selected = await selectFolder("Select Output Root", outputRoot || undefined);
    if (selected) {
      setOutputRoot(selected);
    }
  }

  async function runRuntimeValidation() {
    setError("");
    setBusy("Validating selected folders...");
    try {
      if (!effectiveScenarioFolder.trim()) {
        throw new Error("Select Configuration.netsim (or enter scenario folder path) before validation.");
      }
      if (!netsimBinPath.trim()) {
        throw new Error("Select NetSimCore.exe path before validation.");
      }
      const validation = await validateRuntimePaths({
        scenario_folder: effectiveScenarioFolder,
        netsim_bin_path: netsimBinPath,
        output_root: outputRoot || null,
      });
      setRuntimeValidation(validation);
      if (validation.scenario_folder.valid) {
        setScenarioFolder(validation.scenario_folder.path);
        if (!selectedConfig) {
          setSelectedConfig(joinPath(validation.scenario_folder.path, "Configuration.netsim"));
        }
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  async function loadInputCatalog() {
    if (!selectedConfig) return;
    setError("");
    setBusy("Loading input parameters...");
    try {
      const [inputs, hierarchy] = await Promise.all([
        discoverInputParameters(selectedConfig),
        discoverInputHierarchy(selectedConfig),
      ]);
      setInputCandidates(inputs);
      setInputHierarchy(hierarchy);
      const nextInputs: Record<string, InputSpecUI> = {};
      inputs.forEach((item) => {
        nextInputs[item.parameter_id] = defaultInputSpec(item);
      });
      setInputSpecState(nextInputs);
      const firstSection = hierarchy[0];
      setSelectedInputSectionId(firstSection?.section_id ?? "");
      setSelectedInputEntityId(preferredEntityId(firstSection ?? null));
      setSelectedInputLayerKey("__all__");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  async function loadOutputCatalog() {
    if (!selectedConfig) return;
    setError("");
    setBusy("Loading output metrics...");
    try {
      const outputs = await discoverOutputParameters(selectedConfig, {
        generateMetricsIfMissing: autoGenerateMetrics,
        persistGeneratedMetrics,
        bootstrapSession: {
          scenario_folder: effectiveScenarioFolder,
          netsim_bin_path: netsimBinPath,
          output_root: outputRoot || null,
          license: {
            mode: licenseMode,
            license_server: licenseMode === "license_server" ? licenseServer : null,
            license_file_path: licenseMode === "license_file" ? licenseFilePath : null,
          },
        },
      });
      setOutputCandidates(outputs.items);
      setWarnings(outputs.warnings);
      setDiscoveredMetricsPath(outputs.metrics_path || "");
      const nextOutputs: Record<string, boolean> = {};
      outputs.items.forEach((item) => {
        nextOutputs[item.metric_id] = false;
      });
      setSelectedOutputs(nextOutputs);
      setOutputMenuFilter("__all__");
      setOutputTableFilter("__all__");
      setOutputSourceFilter("__all__");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  function patchInputSpec(parameterId: string, patch: Partial<InputSpecUI>, item?: InputCandidate) {
    setInputSpecState((prev) => {
      const existing = prev[parameterId];
      const base = item ? defaultInputSpec(item) : existing ?? defaultInputSpec({
        parameter_id: parameterId,
        category: "Other",
        label: parameterId,
        node_path: "",
        attribute_name: "",
        current_value: "",
        value_type: "string",
      });
      return {
        ...prev,
        [parameterId]: { ...base, ...existing, ...patch },
      };
    });
  }

  function addInputParameter(item: InputCandidate) {
    patchInputSpec(item.parameter_id, { selected: true }, item);
  }

  function removeInputParameter(parameterId: string) {
    patchInputSpec(parameterId, { selected: false });
  }

  function addOutputParameter(metricId: string) {
    setSelectedOutputs((prevState) => ({ ...prevState, [metricId]: true }));
  }

  function removeOutputParameter(metricId: string) {
    setSelectedOutputs((prevState) => ({ ...prevState, [metricId]: false }));
  }

  async function autoGenerateValueTemplate(parameterId: string) {
    setBusy("Generating sample value file template...");
    try {
      const suggested = `E:\\Codex\\Simulation\\tools\\netsim_sweeper_web_mvp\\value_template_${parameterId.replace(
        /[^\w.-]+/g,
        "_"
      )}.csv`;
      const createdPath = await generateValueTemplate(suggested);
      patchInputSpec(parameterId, { filePath: createdPath.trim() });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  function buildValueSpecPayload(item: InputCandidate, spec: InputSpecUI) {
    if (spec.mode === "fixed") {
      const values = splitCsvValues(spec.fixedValues || item.current_value);
      if (!values.length) {
        throw new Error(`Fixed values are empty for ${item.label}.`);
      }
      return { mode: "fixed", values };
    }
    if (spec.mode === "range") {
      const start = parseNumber(spec.rangeStart);
      const end = parseNumber(spec.rangeEnd);
      const step = parseNumber(spec.rangeStep);
      if (start === null || end === null || step === null || step === 0) {
        throw new Error(`Range requires valid start/end/step for ${item.label}.`);
      }
      if (spec.numberKind === "integer" && (!Number.isInteger(start) || !Number.isInteger(end) || !Number.isInteger(step))) {
        throw new Error(`Range integer mode requires integer start/end/step for ${item.label}.`);
      }
      return {
        mode: "range",
        start,
        end,
        step,
        integer_only: spec.numberKind === "integer",
      };
    }
    if (spec.mode === "random") {
      const minimum = parseNumber(spec.randomMin);
      const maximum = parseNumber(spec.randomMax);
      const count = parseInteger(spec.randomCount);
      const seed = spec.randomSeed.trim() ? parseInteger(spec.randomSeed) : null;
      if (minimum === null || maximum === null || count === null || count <= 0) {
        throw new Error(`Random mode requires valid min/max/count for ${item.label}.`);
      }
      if (seed === null && spec.randomSeed.trim()) {
        throw new Error(`Random seed must be integer for ${item.label}.`);
      }
      return {
        mode: "random",
        minimum,
        maximum,
        count,
        seed,
        integer_only: spec.numberKind === "integer",
      };
    }
    if (spec.mode === "from_file") {
      const filePath = spec.filePath.trim();
      if (!filePath) {
        throw new Error(`File path is required for ${item.label} in from_file mode.`);
      }
      return { mode: "from_file", file_path: filePath };
    }
    throw new Error(`Unsupported mode for ${item.label}.`);
  }

  const activeInputSection = useMemo(
    () => inputHierarchy.find((section) => section.section_id === selectedInputSectionId) ?? null,
    [inputHierarchy, selectedInputSectionId]
  );

  const activeInputEntity = useMemo(() => {
    if (!activeInputSection) return null;
    return activeInputSection.entities.find((entity) => entity.entity_id === selectedInputEntityId) ?? null;
  }, [activeInputSection, selectedInputEntityId]);

  useEffect(() => {
    if (!inputHierarchy.length) {
      setSelectedInputSectionId("");
      setSelectedInputEntityId("");
      setSelectedInputLayerKey("__all__");
      return;
    }
    const hasSection = inputHierarchy.some((section) => section.section_id === selectedInputSectionId);
    if (!hasSection) {
      const firstSection = inputHierarchy[0];
      setSelectedInputSectionId(firstSection.section_id);
      setSelectedInputEntityId(preferredEntityId(firstSection));
      setSelectedInputLayerKey("__all__");
    }
  }, [inputHierarchy, selectedInputSectionId]);

  useEffect(() => {
    if (!activeInputSection) {
      setSelectedInputEntityId("");
      setSelectedInputLayerKey("__all__");
      return;
    }
    const hasEntity = activeInputSection.entities.some((entity) => entity.entity_id === selectedInputEntityId);
    if (!hasEntity) {
      setSelectedInputEntityId(preferredEntityId(activeInputSection));
      setSelectedInputLayerKey("__all__");
    }
  }, [activeInputSection, selectedInputEntityId]);

  useEffect(() => {
    if (!activeInputEntity) {
      setSelectedInputLayerKey("__all__");
      return;
    }
    if (selectedInputLayerKey === "__all__") return;
    const hasLayer = activeInputEntity.layers.some((layer) => layer.layer_key === selectedInputLayerKey);
    if (!hasLayer) {
      setSelectedInputLayerKey("__all__");
    }
  }, [activeInputEntity, selectedInputLayerKey]);

  const visibleInputParameters = useMemo(() => {
    if (!activeInputEntity) return [] as InputCandidate[];
    const layerItems =
      selectedInputLayerKey === "__all__"
        ? activeInputEntity.layers.flatMap((layer) => layer.parameters)
        : activeInputEntity.layers.find((layer) => layer.layer_key === selectedInputLayerKey)?.parameters ?? [];
    const text = inputFilter.trim().toLowerCase();
    return layerItems.filter((item) =>
      text ? `${item.category} ${item.label} ${item.parameter_id}`.toLowerCase().includes(text) : true
    );
  }, [activeInputEntity, selectedInputLayerKey, inputFilter]);

  const inputParameterContext = useMemo(() => {
    const map: Record<string, { section: string; entity: string; layer: string }> = {};
    inputHierarchy.forEach((section) => {
      section.entities.forEach((entity) => {
        entity.layers.forEach((layer) => {
          layer.parameters.forEach((parameter) => {
            map[parameter.parameter_id] = {
              section: section.section_label,
              entity: entity.entity_label,
              layer: layer.layer_label,
            };
          });
        });
      });
    });
    return map;
  }, [inputHierarchy]);

  const outputMenuOptions = useMemo(() => {
    return Array.from(new Set(outputCandidates.map((item) => item.menu_name))).sort((a, b) =>
      a.localeCompare(b)
    );
  }, [outputCandidates]);

  const outputTableOptions = useMemo(() => {
    const scoped = outputCandidates.filter((item) =>
      outputMenuFilter === "__all__" ? true : item.menu_name === outputMenuFilter
    );
    return Array.from(new Set(scoped.map((item) => item.table_name))).sort((a, b) => a.localeCompare(b));
  }, [outputCandidates, outputMenuFilter]);

  useEffect(() => {
    if (outputMenuFilter === "__all__") return;
    if (!outputMenuOptions.includes(outputMenuFilter)) {
      setOutputMenuFilter("__all__");
    }
  }, [outputMenuOptions, outputMenuFilter]);

  useEffect(() => {
    if (outputTableFilter === "__all__") return;
    if (!outputTableOptions.includes(outputTableFilter)) {
      setOutputTableFilter("__all__");
    }
  }, [outputTableOptions, outputTableFilter]);

  const visibleOutputs = useMemo(() => {
    const text = outputFilter.trim().toLowerCase();
    return outputCandidates
      .filter((item) => {
        if (outputMenuFilter !== "__all__" && item.menu_name !== outputMenuFilter) return false;
        if (outputTableFilter !== "__all__" && item.table_name !== outputTableFilter) return false;
        if (outputSourceFilter !== "__all__" && item.source_type !== outputSourceFilter) return false;
        if (!text) return true;
        return `${item.menu_name} ${item.table_name} ${item.column_name} ${item.source_type}`
          .toLowerCase()
          .includes(text);
      })
      .sort((a, b) => {
        const menuCmp = a.menu_name.localeCompare(b.menu_name);
        if (menuCmp !== 0) return menuCmp;
        const tableCmp = a.table_name.localeCompare(b.table_name);
        if (tableCmp !== 0) return tableCmp;
        return a.column_name.localeCompare(b.column_name);
      });
  }, [outputFilter, outputCandidates, outputMenuFilter, outputTableFilter, outputSourceFilter]);

  const selectedInputCandidates = useMemo(
    () => inputCandidates.filter((item) => inputSpecState[item.parameter_id]?.selected),
    [inputCandidates, inputSpecState]
  );
  const selectedOutputCandidates = useMemo(
    () => outputCandidates.filter((item) => selectedOutputs[item.metric_id]),
    [outputCandidates, selectedOutputs]
  );

  const inputDimensionEstimate = useMemo(() => {
    if (!selectedInputCandidates.length) return 0;
    if (!linkCommonLabels) {
      return selectedInputCandidates.reduce((product, item) => {
        const spec = inputSpecState[item.parameter_id] ?? defaultInputSpec(item);
        const count = estimateSpecCount(spec);
        return product * count;
      }, 1);
    }
    const groupMap = new Map<string, InputCandidate[]>();
    selectedInputCandidates.forEach((item) => {
      const group = groupMap.get(item.label) || [];
      group.push(item);
      groupMap.set(item.label, group);
    });
    let product = 1;
    for (const group of groupMap.values()) {
      const master = group[0];
      const spec = inputSpecState[master.parameter_id] ?? defaultInputSpec(master);
      const count = estimateSpecCount(spec);
      product *= count;
    }
    return product;
  }, [selectedInputCandidates, linkCommonLabels, inputSpecState]);

  const hasFileBasedInputSpec = useMemo(
    () =>
      selectedInputCandidates.some((item) => (inputSpecState[item.parameter_id] ?? defaultInputSpec(item)).mode === "from_file"),
    [selectedInputCandidates, inputSpecState]
  );

  async function createAndStartJob() {
    if (!selectedConfig) return;
    setError("");
    setBusy("Creating and starting sweep...");
    try {
      if (!runtimeValidation?.all_valid) {
        throw new Error("Runtime validation has not passed. Validate folders before starting.");
      }
      if (selectedInputCandidates.length === 0) {
        throw new Error("Select at least one input parameter.");
      }
      if (inputDimensionEstimate <= 0) {
        throw new Error("At least one selected input parameter has invalid/empty value specification.");
      }
      if (inputDimensionEstimate > 2000) {
        throw new Error(
          `Planned combinations (${inputDimensionEstimate}) exceed server cap 2000. Reduce parameter combinations.`
        );
      }
      if (inputDimensionEstimate > maxRuns) {
        throw new Error(
          `Planned combinations (${inputDimensionEstimate}) exceed max_runs (${maxRuns}). Increase max_runs or reduce input combinations.`
        );
      }
      if (maxRuns > 2000) {
        throw new Error("max_runs cannot exceed 2000.");
      }

      const selectedOutputPayload = selectedOutputCandidates.map((item) => ({
        metric_id: item.metric_id,
        label: `${item.menu_name} / ${item.column_name}`,
        source_type: item.source_type,
        row_filters: {},
      }));
      if (selectedOutputPayload.length === 0) {
        throw new Error("Select at least one output parameter.");
      }

      let selectedInputPayload: Array<{
        parameter_id: string;
        label: string;
        apply_to_parameter_ids: string[];
        value_spec: Record<string, unknown>;
      }> = [];

      if (!linkCommonLabels) {
        selectedInputPayload = selectedInputCandidates.map((item) => ({
          parameter_id: item.parameter_id,
          label: item.label,
          apply_to_parameter_ids: [],
          value_spec: buildValueSpecPayload(item, inputSpecState[item.parameter_id] ?? defaultInputSpec(item)),
        }));
      } else {
        const groupMap = new Map<string, InputCandidate[]>();
        selectedInputCandidates.forEach((item) => {
          const group = groupMap.get(item.label) || [];
          group.push(item);
          groupMap.set(item.label, group);
        });
        selectedInputPayload = Array.from(groupMap.entries()).map(([label, group]) => {
          const master = group[0];
          return {
            parameter_id: master.parameter_id,
            label: `${label}${group.length > 1 ? ` (linked x${group.length})` : ""}`,
            apply_to_parameter_ids: group.slice(1).map((item) => item.parameter_id),
            value_spec: buildValueSpecPayload(
              master,
              inputSpecState[master.parameter_id] ?? defaultInputSpec(master)
            ),
          };
        });
      }

      const payload = {
        session: {
          scenario_folder: effectiveScenarioFolder,
          netsim_bin_path: netsimBinPath,
          output_root: outputRoot || null,
          license: {
            mode: licenseMode,
            license_server: licenseMode === "license_server" ? licenseServer : null,
            license_file_path: licenseMode === "license_file" ? licenseFilePath : null,
          },
        },
        configuration_path: selectedConfig,
        metrics_path: discoveredMetricsPath || null,
        input_parameters: selectedInputPayload,
        output_parameters: selectedOutputPayload,
        include_patterns: [],
        exclude_patterns: [],
        max_runs: maxRuns,
        execute_mode: executeMode,
      };

      setConsoleLines([]);
      setCsvPreview(null);
      const created = await createJob(payload);
      setJob(created);
      await startJob(created.job_id);
      subscribeToJob(created.job_id);
      await refreshSavedRuns();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  async function cancelCurrentJob() {
    if (!job) return;
    setBusy("Requesting cancellation...");
    try {
      await cancelJob(job.job_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  async function resumeCurrentJob() {
    if (!job) return;
    setBusy("Resuming pending/incomplete runs...");
    try {
      await resumeJob(job.job_id);
      subscribeToJob(job.job_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  async function retryFailedRuns() {
    if (!job) return;
    setBusy("Retrying failed runs...");
    try {
      await retryFailedJob(job.job_id);
      subscribeToJob(job.job_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  async function loadCsvPreview() {
    if (!job) return;
    setBusy("Loading sweep_result.csv preview...");
    try {
      const preview = await getResultCsv(job.job_id, 300);
      setCsvPreview(preview);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  async function openCsvInDesktop() {
    if (!job) return;
    try {
      await openResultCsv(job.job_id);
    } catch (err) {
      setError(String(err));
    }
  }

  async function loadSavedJob(jobId: string) {
    setBusy("Loading saved run...");
    try {
      const loaded = await getJob(jobId);
      setJob(loaded);
      setConsoleLines([]);
      setCsvPreview(null);
      if (loaded.status === "running") {
        subscribeToJob(jobId);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  async function renameSavedRun(item: SweepJob) {
    const currentName = getDisplayRunName(item);
    const next = window.prompt("Enter new run name", currentName);
    if (next === null) return;
    const trimmed = next.trim();
    if (!trimmed) {
      setError("Run name cannot be empty.");
      return;
    }
    setBusy("Renaming saved run...");
    try {
      await renameJob(item.job_id, trimmed);
      await refreshSavedRuns();
      if (job?.job_id === item.job_id) {
        const latest = await getJob(item.job_id);
        setJob(latest);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy("");
    }
  }

  const progressPct = job
    ? Math.round(
        ((job.completed_run_count + job.failed_run_count + job.cancelled_run_count) /
          Math.max(job.planned_run_count, 1)) *
          100
      )
    : 0;

  const metricIds = useMemo(() => {
    if (!job) return [] as string[];
    const first = job.runs.find((run) => Object.keys(run.outputs || {}).length > 0);
    return first ? Object.keys(first.outputs || {}) : [];
  }, [job]);

  useEffect(() => {
    if (!metricIds.length) return;
    setPlotSelection((prev) => {
      const next = { ...prev };
      let hasAny = false;
      metricIds.forEach((metric) => {
        if (!(metric in next)) next[metric] = true;
        if (next[metric]) hasAny = true;
      });
      if (!hasAny && metricIds.length) next[metricIds[0]] = true;
      return next;
    });
    setPlotMetricUnits((prev) => {
      const next = { ...prev };
      metricIds.forEach((metric) => {
        if (!(metric in next)) next[metric] = "";
      });
      return next;
    });
  }, [metricIds]);

  const selectedPlotMetrics = metricIds.filter((id) => plotSelection[id]);
  const outputById = useMemo(() => {
    const map: Record<string, OutputCandidate> = {};
    outputCandidates.forEach((candidate) => {
      map[candidate.metric_id] = candidate;
    });
    return map;
  }, [outputCandidates]);
  const metricDisplayNameById = useMemo(() => {
    const baseById: Record<string, string> = {};
    metricIds.forEach((metricId) => {
      const candidate = outputById[metricId];
      baseById[metricId] = candidate?.column_name?.trim() || metricLeafLabel(metricId);
    });
    const counts: Record<string, number> = {};
    Object.values(baseById).forEach((base) => {
      counts[base] = (counts[base] || 0) + 1;
    });
    const labels: Record<string, string> = {};
    metricIds.forEach((metricId) => {
      const base = baseById[metricId];
      if ((counts[base] || 0) <= 1) {
        labels[metricId] = base;
        return;
      }
      const candidate = outputById[metricId];
      const context = candidate
        ? `${candidate.menu_name} / ${candidate.table_name}`
        : metricContextLabel(metricId);
      labels[metricId] = context ? `${base} (${context})` : `${base} (${metricId})`;
    });
    return labels;
  }, [metricIds, outputById]);
  const plotSeries = selectedPlotMetrics.map((metricId) => ({
    metricId,
    label: metricDisplayNameById[metricId] || metricLeafLabel(metricId),
    values:
      job?.runs.map((run) => {
        const value = run.outputs[metricId];
        return typeof value === "number" ? value : null;
      }) || [],
  }));
  const selectedMetricUnits = selectedPlotMetrics
    .map((metricId) => (plotMetricUnits[metricId] || "").trim())
    .filter(Boolean);
  const combinedYUnit =
    new Set(selectedMetricUnits).size === 1
      ? selectedMetricUnits[0]
      : new Set(selectedMetricUnits).size > 1
        ? "mixed"
        : "";

  return (
    <main className="page">
      <header className="hero">
        <h1>NetSim Multi-Parameter Sweeper</h1>
        <p>Use local folder browse, runtime validation, live console, and saved runs for iterative analysis.</p>
      </header>

      <section className="card">
        <h2>1. Runtime Setup</h2>
        <div className="grid grid-3">
          <label>
            <span className="field-label">
              Scenario folder
              <HelpTip text="Browse opens a file picker for Configuration.netsim. The parent folder is used as scenario folder." />
            </span>
            <div className="input-row">
              <input value={scenarioFolder} onChange={(e) => setScenarioFolder(e.target.value)} />
              <button type="button" onClick={browseScenarioFolder}>
                Browse Configuration
              </button>
            </div>
          </label>
          <label>
            <span className="field-label">
              NetSimCore executable
              <HelpTip text="Browse and select NetSimCore.exe. This exact file path will be used for live execution." />
            </span>
            <div className="input-row">
              <input value={netsimBinPath} onChange={(e) => setNetsimBinPath(e.target.value)} />
              <button type="button" onClick={browseNetsimBin}>
                Browse NetSimCore
              </button>
            </div>
          </label>
          <label>
            <span className="field-label">
              Output root
              <HelpTip text="Default is Documents\\NetSim Multi-Parameter Sweeper. You can override it." />
            </span>
            <div className="input-row">
              <input value={outputRoot} onChange={(e) => setOutputRoot(e.target.value)} />
              <button type="button" onClick={browseOutputRoot}>
                Browse
              </button>
            </div>
            {defaultOutputRoot && <span className="mono">Default: {defaultOutputRoot}</span>}
          </label>
        </div>

        <div className="grid grid-4">
          <label>
            <span className="field-label">
              License mode
              <HelpTip text="Choose license server or local license file mode." />
            </span>
            <select value={licenseMode} onChange={(e) => setLicenseMode(e.target.value as "license_server" | "license_file")}>
              <option value="license_server">License server</option>
              <option value="license_file">License file path</option>
            </select>
          </label>
          <label>
            {licenseMode === "license_server" ? "Server (port@ip)" : "License file path"}
            <input
              value={licenseMode === "license_server" ? licenseServer : licenseFilePath}
              onChange={(e) =>
                licenseMode === "license_server"
                  ? setLicenseServer(e.target.value)
                  : setLicenseFilePath(e.target.value)
              }
            />
          </label>
          <label>
            <span className="field-label">
              Execute mode
              <HelpTip text="dry_run uses synthetic outputs, live runs NetSimcore.exe per run." />
            </span>
                <select value={executeMode} onChange={(e) => setExecuteMode(e.target.value as "dry_run" | "live")}>
                  <option value="live">Live NetSim</option>
                  <option value="dry_run">Dry Run</option>
                </select>
              </label>
              <label>
                <span className="field-label">
                  Max runs
                  <HelpTip text="Upper safety cap for generated combinations. Default 2000. Server cap is 2000." />
                </span>
            <input
              type="number"
              min={1}
              max={2000}
              value={maxRuns}
              onChange={(e) => {
                const next = Number(e.target.value);
                if (!Number.isFinite(next)) return;
                setMaxRuns(Math.max(1, Math.min(2000, Math.floor(next))));
              }}
            />
              </label>
          <label>
            <span className="field-label">
              Auto-generate Metrics.xml
              <HelpTip text="If Metrics.xml is missing, perform one bootstrap run for discovery." />
            </span>
            <select
              value={autoGenerateMetrics ? "yes" : "no"}
              onChange={(e) => setAutoGenerateMetrics(e.target.value === "yes")}
            >
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </label>
          <label>
            <span className="field-label">
              Persist bootstrap metrics
              <HelpTip text="If yes, generated Metrics.xml is copied back to scenario folder." />
            </span>
            <select
              value={persistGeneratedMetrics ? "yes" : "no"}
              onChange={(e) => setPersistGeneratedMetrics(e.target.value === "yes")}
            >
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </select>
          </label>
        </div>

        <div className="actions">
          <button onClick={runRuntimeValidation}>Validate Runtime Paths</button>
          <button onClick={() => setOutputRoot(defaultOutputRoot)} disabled={!defaultOutputRoot}>
            Use Default Output Root
          </button>
          <button onClick={refreshSavedRuns}>Refresh Saved Runs</button>
        </div>

        {runtimeValidation && (
          <div className="validation-grid">
            <div className={runtimeValidation.scenario_folder.valid ? "ok" : "bad"}>
              Scenario: {runtimeValidation.scenario_folder.message}
            </div>
            <div className={runtimeValidation.netsim_bin_path.valid ? "ok" : "bad"}>
              NetSim bin: {runtimeValidation.netsim_bin_path.message}
            </div>
            <div className={runtimeValidation.output_root.valid ? "ok" : "bad"}>
              Output root: {runtimeValidation.output_root.message}
            </div>
          </div>
        )}
        {selectedConfig && <p className="mono">Selected configuration: {selectedConfig}</p>}
      </section>

      <section className="card">
        <h2>2. Input Parameters</h2>
        <div className="actions">
          <button onClick={loadInputCatalog} disabled={!selectedConfig}>
            Load Input Parameters
          </button>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={linkCommonLabels}
              onChange={(e) => setLinkCommonLabels(e.target.checked)}
            />
            Treat common property labels as one parameter
            <HelpTip text="If selected, parameters with the same label are linked and receive the same value in each run." />
          </label>
        </div>
        <div className="grid grid-3">
          <label>
            <span className="field-label">
              Section
              <HelpTip text="Choose Device/Link/Application/Simulation/Grid section to narrow parameter discovery." />
            </span>
            <select
              value={selectedInputSectionId}
              onChange={(e) => {
                setSelectedInputSectionId(e.target.value);
                setSelectedInputLayerKey("__all__");
              }}
              disabled={!inputHierarchy.length}
            >
              {inputHierarchy.map((section) => (
                <option key={section.section_id} value={section.section_id}>
                  {section.section_label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">
              Entity
              <HelpTip text="For Device section this is device list, for Links it is link list, for Applications it is app list." />
            </span>
            <select
              value={selectedInputEntityId}
              onChange={(e) => {
                setSelectedInputEntityId(e.target.value);
                setSelectedInputLayerKey("__all__");
              }}
              disabled={!activeInputSection?.entities.length}
            >
              {(activeInputSection?.entities || []).map((entity) => (
                <option key={entity.entity_id} value={entity.entity_id}>
                  {entity.entity_label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">
              Layer
              <HelpTip text="Filter selected entity parameters by Application/Transport/Network/Interface/Physical etc." />
            </span>
            <select
              value={selectedInputLayerKey}
              onChange={(e) => setSelectedInputLayerKey(e.target.value)}
              disabled={!activeInputEntity}
            >
              <option value="__all__">All layers</option>
              {(activeInputEntity?.layers || []).map((layer) => (
                <option key={layer.layer_key} value={layer.layer_key}>
                  {layer.layer_label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Filter inputs
          <input value={inputFilter} onChange={(e) => setInputFilter(e.target.value)} />
        </label>
        <div className="table">
          {visibleInputParameters.slice(0, 400).map((item) => {
            const state = inputSpecState[item.parameter_id] ?? defaultInputSpec(item);
            const meta = inputParameterContext[item.parameter_id];
            return (
              <div className="row input-candidate-row" key={item.parameter_id}>
                <span className="mono">{meta?.layer || item.category}</span>
                <span className="mono">{item.label}</span>
                <input
                  value={state.fixedValues}
                  onChange={(e) => patchInputSpec(item.parameter_id, { fixedValues: e.target.value }, item)}
                />
                <span className="actions-inline">
                  <button type="button" onClick={() => addInputParameter(item)}>
                    {state.selected ? "Update" : "Add"}
                  </button>
                </span>
              </div>
            );
          })}
        </div>
        {!visibleInputParameters.length && <p className="mono">No parameters available for current section/entity/layer.</p>}
        <h3>Selected Parameters</h3>
        <div className="table compact">
          {selectedInputCandidates.map((item) => {
            const state = inputSpecState[item.parameter_id] ?? { ...defaultInputSpec(item), selected: true };
            const meta = inputParameterContext[item.parameter_id];
            return (
              <div className="row selected-input-row" key={`selected-${item.parameter_id}`}>
                <span className="mono">{meta ? `${meta.section} / ${meta.entity}` : item.category}</span>
                <span className="mono">{item.label}</span>
                <div className="spec-editor">
                  <select
                    value={state.mode}
                    onChange={(e) =>
                      patchInputSpec(
                        item.parameter_id,
                        { mode: e.target.value as InputMode },
                        item
                      )
                    }
                  >
                    <option value="fixed">Fixed list</option>
                    <option value="range">Range</option>
                    <option value="random">Random</option>
                    <option value="from_file">From file</option>
                  </select>
                  {state.mode === "fixed" && (
                    <input
                      value={state.fixedValues}
                      onChange={(e) => patchInputSpec(item.parameter_id, { fixedValues: e.target.value }, item)}
                      placeholder="Comma-separated values"
                    />
                  )}
                  {state.mode === "range" && (
                    <>
                      <input
                        value={state.rangeStart}
                        onChange={(e) => patchInputSpec(item.parameter_id, { rangeStart: e.target.value }, item)}
                        placeholder="start"
                      />
                      <input
                        value={state.rangeEnd}
                        onChange={(e) => patchInputSpec(item.parameter_id, { rangeEnd: e.target.value }, item)}
                        placeholder="end"
                      />
                      <input
                        value={state.rangeStep}
                        onChange={(e) => patchInputSpec(item.parameter_id, { rangeStep: e.target.value }, item)}
                        placeholder="step"
                      />
                      <select
                        value={state.numberKind}
                        onChange={(e) =>
                          patchInputSpec(
                            item.parameter_id,
                            { numberKind: e.target.value as "float" | "integer" },
                            item
                          )
                        }
                      >
                        <option value="float">Float</option>
                        <option value="integer">Integer</option>
                      </select>
                    </>
                  )}
                  {state.mode === "random" && (
                    <>
                      <input
                        value={state.randomMin}
                        onChange={(e) => patchInputSpec(item.parameter_id, { randomMin: e.target.value }, item)}
                        placeholder="min"
                      />
                      <input
                        value={state.randomMax}
                        onChange={(e) => patchInputSpec(item.parameter_id, { randomMax: e.target.value }, item)}
                        placeholder="max"
                      />
                      <input
                        value={state.randomCount}
                        onChange={(e) => patchInputSpec(item.parameter_id, { randomCount: e.target.value }, item)}
                        placeholder="count"
                      />
                      <input
                        value={state.randomSeed}
                        onChange={(e) => patchInputSpec(item.parameter_id, { randomSeed: e.target.value }, item)}
                        placeholder="seed"
                      />
                      <select
                        value={state.numberKind}
                        onChange={(e) =>
                          patchInputSpec(
                            item.parameter_id,
                            { numberKind: e.target.value as "float" | "integer" },
                            item
                          )
                        }
                      >
                        <option value="float">Float</option>
                        <option value="integer">Integer</option>
                      </select>
                    </>
                  )}
                  {state.mode === "from_file" && (
                    <>
                      <input
                        value={state.filePath}
                        onChange={(e) => patchInputSpec(item.parameter_id, { filePath: e.target.value }, item)}
                        placeholder="Path to CSV with value column"
                      />
                      <button type="button" onClick={() => void autoGenerateValueTemplate(item.parameter_id)}>
                        Template
                      </button>
                    </>
                  )}
                </div>
                <span className="actions-inline">
                  <button type="button" onClick={() => removeInputParameter(item.parameter_id)}>
                    Remove
                  </button>
                </span>
              </div>
            );
          })}
        </div>
        {!selectedInputCandidates.length && <p className="mono">No input parameters selected yet.</p>}
      </section>

      <section className="card">
        <h2>3. Output Metrics</h2>
        <div className="actions">
          <button onClick={loadOutputCatalog} disabled={!selectedConfig}>
            Load Output Metrics
          </button>
          <button
            type="button"
            onClick={() => {
              const updates: Record<string, boolean> = {};
              visibleOutputs.forEach((item) => {
                updates[item.metric_id] = true;
              });
              setSelectedOutputs((prev) => ({ ...prev, ...updates }));
            }}
            disabled={!visibleOutputs.length}
          >
            Select Visible
          </button>
          <button
            type="button"
            onClick={() => {
              const updates: Record<string, boolean> = {};
              visibleOutputs.forEach((item) => {
                updates[item.metric_id] = false;
              });
              setSelectedOutputs((prev) => ({ ...prev, ...updates }));
            }}
            disabled={!visibleOutputs.length}
          >
            Clear Visible
          </button>
        </div>
        {discoveredMetricsPath && <p className="mono">Metrics file: {discoveredMetricsPath}</p>}
        <div className="grid grid-3">
          <label>
            <span className="field-label">
              Section / Menu
              <HelpTip text="Filter output metrics by Metrics.xml MENU section or log menu group." />
            </span>
            <select
              value={outputMenuFilter}
              onChange={(e) => {
                setOutputMenuFilter(e.target.value);
                setOutputTableFilter("__all__");
              }}
              disabled={!outputCandidates.length}
            >
              <option value="__all__">All sections</option>
              {outputMenuOptions.map((menu) => (
                <option key={menu} value={menu}>
                  {menu}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">
              Table
              <HelpTip text="Filter by table within selected section/menu." />
            </span>
            <select
              value={outputTableFilter}
              onChange={(e) => setOutputTableFilter(e.target.value)}
              disabled={!outputCandidates.length}
            >
              <option value="__all__">All tables</option>
              {outputTableOptions.map((table) => (
                <option key={table} value={table}>
                  {table}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">
              Source Type
              <HelpTip text="Filter metrics source: Metrics.xml or log-plugin based outputs." />
            </span>
            <select
              value={outputSourceFilter}
              onChange={(e) =>
                setOutputSourceFilter(e.target.value as "__all__" | "metrics_xml" | "log_plugin")
              }
              disabled={!outputCandidates.length}
            >
              <option value="__all__">All sources</option>
              <option value="metrics_xml">metrics_xml</option>
              <option value="log_plugin">log_plugin</option>
            </select>
          </label>
        </div>
        <label>
          Filter metrics
          <input value={outputFilter} onChange={(e) => setOutputFilter(e.target.value)} />
        </label>
        <div className="table">
          {visibleOutputs.slice(0, 600).map((item, index, arr) => {
            const prev = arr[index - 1];
            const groupChanged =
              !prev || prev.menu_name !== item.menu_name || prev.table_name !== item.table_name;
            return (
              <div key={item.metric_id}>
                {groupChanged && (
                  <div className="row output-group-row">
                    <strong>{item.menu_name}</strong>
                    <span className="mono">{item.table_name}</span>
                    <span className="mono">Table Group</span>
                    <span className="mono">{item.source_type}</span>
                  </div>
                )}
                <div className="row output-candidate-row">
                  <span className="actions-inline">
                    {selectedOutputs[item.metric_id] ? (
                      <button type="button" onClick={() => removeOutputParameter(item.metric_id)}>
                        Remove
                      </button>
                    ) : (
                      <button type="button" onClick={() => addOutputParameter(item.metric_id)}>
                        Add
                      </button>
                    )}
                  </span>
                  <span className="mono">{item.menu_name}</span>
                  <span className="mono">{item.table_name}</span>
                  <span>{item.column_name}</span>
                  <span className={`mono ${item.available_now === false ? "warning" : ""}`}>
                    {item.source_type}
                    {item.available_now === false ? " (will appear after run)" : ""}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
        {!visibleOutputs.length && <p className="mono">No output metrics match current section/table/source filters.</p>}
        <h3>Selected Output Parameters</h3>
        <div className="table compact">
          {selectedOutputCandidates.map((item) => (
            <div className="row selected-output-row" key={`selected-${item.metric_id}`}>
              <span className="mono">{item.menu_name}</span>
              <span className="mono">{item.table_name}</span>
              <span className="mono">
                {item.column_name} [{item.source_type}]
              </span>
              <span className="actions-inline">
                <button type="button" onClick={() => removeOutputParameter(item.metric_id)}>
                  Remove
                </button>
              </span>
            </div>
          ))}
        </div>
        {!selectedOutputCandidates.length && <p className="mono">No output parameters selected yet.</p>}
      </section>

      <section className="card">
        <h2>4. Sweep Plan & Launch</h2>
        <p>
          Planned runs = Cartesian product across selected input dimensions. If two parameters have two values each,
          runs = <strong>4</strong>.
        </p>
        <p>
          Current estimate: <strong>{inputDimensionEstimate || 0}</strong> runs
          {inputDimensionEstimate > maxRuns ? " (exceeds max_runs)" : ""}
        </p>
        {hasFileBasedInputSpec && (
          <p className="warning">
            File-based input mode selected for at least one parameter. Estimated run count may be lower than actual.
          </p>
        )}
        {inputDimensionEstimate > maxRuns && (
          <p className="warning">
            Planned combinations exceed current max_runs. Increase max_runs (up to 2000) or reduce parameter combinations.
          </p>
        )}
        {inputDimensionEstimate > maxRuns && inputDimensionEstimate <= 2000 && (
          <div className="actions">
            <button type="button" onClick={() => setMaxRuns(inputDimensionEstimate)}>
              Set max_runs to {inputDimensionEstimate}
            </button>
          </div>
        )}
        {inputDimensionEstimate > 2000 && (
          <p className="warning">
            Planned combinations exceed server cap 2000. Reduce parameter combinations before starting.
          </p>
        )}
        <div className="actions">
          <button onClick={createAndStartJob}>Create + Start Sweep</button>
          {job && (
            <>
              <button onClick={cancelCurrentJob} disabled={job.status !== "running"}>
                Cancel
              </button>
              <button onClick={resumeCurrentJob} disabled={job.status === "running"}>
                Resume Pending
              </button>
              <button onClick={retryFailedRuns} disabled={job.status === "running" || job.failed_run_count === 0}>
                Retry Failed
              </button>
            </>
          )}
        </div>
      </section>

      <section className="card">
        <h2>5. Dashboard</h2>
        {job ? (
          <>
            <div className="kpis">
              <div>
                <strong>Run Name</strong>
                <span className="mono">{getDisplayRunName(job)}</span>
              </div>
              <div>
                <strong>Job ID</strong>
                <span className="mono">{job.job_id}</span>
              </div>
              <div>
                <strong>Status</strong>
                <span>{job.status}</span>
              </div>
              <div>
                <strong>Progress / Runs</strong>
                <span>
                  {progressPct}% ({job.completed_run_count}/{job.planned_run_count})
                </span>
              </div>
            </div>
            <div className="progress">
              <div style={{ width: `${progressPct}%` }} />
            </div>

            <div className="actions">
              <label>
                <span className="field-label">
                  Plot mode
                  <HelpTip text="Separate mode renders one chart per metric; combined mode overlays selected metrics." />
                </span>
                <select value={plotMode} onChange={(e) => setPlotMode(e.target.value as "separate" | "combined")}>
                  <option value="separate">Separate plots</option>
                  <option value="combined">Combined plot</option>
                </select>
              </label>
              <label>
                <span className="field-label">X axis title</span>
                <input value={plotXAxisTitle} onChange={(e) => setPlotXAxisTitle(e.target.value)} />
              </label>
              <label>
                <span className="field-label">X unit</span>
                <input value={plotXAxisUnit} onChange={(e) => setPlotXAxisUnit(e.target.value)} />
              </label>
              <label>
                <span className="field-label">Combined Y axis title</span>
                <input value={plotCombinedYAxisTitle} onChange={(e) => setPlotCombinedYAxisTitle(e.target.value)} />
              </label>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={plotShowMarkers}
                  onChange={(e) => setPlotShowMarkers(e.target.checked)}
                />
                Show data markers
              </label>
            </div>
            <p className="mono">
              Iteration range: 1 to {Math.max(job.planned_run_count, 1)}
            </p>
            <div className="plot-selector">
              {metricIds.map((metric) => (
                <label key={metric} className="plot-metric-row">
                  <span className="inline-check mono">
                    <input
                      type="checkbox"
                      checked={!!plotSelection[metric]}
                      onChange={(e) => setPlotSelection((prev) => ({ ...prev, [metric]: e.target.checked }))}
                    />
                    {metricDisplayNameById[metric] || metricLeafLabel(metric)}
                  </span>
                  <span className="mono unit-inline">
                    y-unit
                    <input
                      value={plotMetricUnits[metric] || ""}
                      onChange={(e) =>
                        setPlotMetricUnits((prev) => ({
                          ...prev,
                          [metric]: e.target.value,
                        }))
                      }
                    />
                  </span>
                </label>
              ))}
            </div>

            {plotMode === "combined" && selectedPlotMetrics.length > 1 ? (
              <CombinedPlot
                title="Combined metric view"
                series={plotSeries.map((line, index) => ({
                  metricId: line.metricId,
                  label: line.label,
                  values: line.values,
                  color: PLOT_COLORS[index % PLOT_COLORS.length],
                }))}
                xAxisTitle={plotXAxisTitle}
                xUnit={plotXAxisUnit}
                yAxisTitle={plotCombinedYAxisTitle}
                yUnit={combinedYUnit}
                showMarkers={plotShowMarkers}
                iterationCount={Math.max(job.planned_run_count, 1)}
              />
            ) : (
              plotSeries.map((line, index) => (
                <RunPlot
                  key={line.metricId}
                  title={line.label}
                  legendLabel={line.label}
                  values={line.values}
                  color={PLOT_COLORS[index % PLOT_COLORS.length]}
                  xAxisTitle={plotXAxisTitle}
                  xUnit={plotXAxisUnit}
                  yAxisTitle={line.label}
                  yUnit={plotMetricUnits[line.metricId] || ""}
                  showMarkers={plotShowMarkers}
                  iterationCount={Math.max(job.planned_run_count, 1)}
                />
              ))
            )}

            <h3>Run Status</h3>
            <div className="table compact">
              {job.runs.slice(Math.max(0, job.runs.length - 50)).map((run) => (
                <div key={run.run_index} className="row">
                  <span>Run {run.run_index}</span>
                  <span>{run.status}</span>
                  <span>{run.duration_seconds ? `${run.duration_seconds.toFixed(2)} s` : "-"}</span>
                  <span className="error">{run.error_message || ""}</span>
                </div>
              ))}
            </div>

            <h3>Console Output</h3>
            <div className="console">
              {consoleLines.length ? consoleLines.join("\n") : "No console output captured yet."}
            </div>

            <h3>Result CSV</h3>
            <div className="actions">
              <button onClick={loadCsvPreview}>Load CSV in Dashboard</button>
              <button onClick={openCsvInDesktop}>Open CSV</button>
            </div>
            <p className="mono">CSV path: {job.result_csv_path}</p>
            {csvPreview && (
              <div className="csv-preview">
                <p>
                  Showing {csvPreview.rows.length} of {csvPreview.total_rows} rows
                </p>
                <div className="table compact">
                  <div className="row">
                    {csvPreview.headers.map((h) => (
                      <strong key={h}>{h}</strong>
                    ))}
                  </div>
                  {csvPreview.rows.map((row, idx) => (
                    <div className="row" key={idx}>
                      {row.map((value, col) => (
                        <span key={`${idx}-${col}`}>{value}</span>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {job.warnings.map((w) => (
              <p key={w} className="warning">
                {w}
              </p>
            ))}
          </>
        ) : (
          <p>No active job loaded.</p>
        )}
      </section>

      <section className="card">
        <h2>6. Saved Runs</h2>
        <p>Saved jobs are persisted and can be loaded for later analysis.</p>
        <div className="table compact">
          {savedJobs.slice(0, 100).map((saved) => (
            <div key={saved.job_id} className="row saved-row">
              <span className="mono">{getDisplayRunName(saved)}</span>
              <span className="mono">{saved.job_id}</span>
              <span>{saved.status}</span>
              <span>
                {saved.completed_run_count}/{saved.planned_run_count}
              </span>
              <span className="actions-inline">
                <button type="button" onClick={() => void renameSavedRun(saved)}>
                  Rename
                </button>
                <button type="button" onClick={() => void loadSavedJob(saved.job_id)}>
                  Load
                </button>
              </span>
            </div>
          ))}
        </div>
      </section>

      {busy && <div className="status busy">{busy}</div>}
      {error && <div className="status error">{error}</div>}
      {warnings.map((w) => (
        <div key={w} className="status warning">
          {w}
        </div>
      ))}
    </main>
  );
}
