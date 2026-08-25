import { useEffect, useState } from 'react';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

type ClusterSummary = {
  mode: 'demo' | 'live' | 'empty';
  timestamp?: string;
  source?: string;
  cluster: {
    status: string;
    nodes: number;
    readyNodes: number;
    namespaces: number;
    pods: {
      running: number;
      pending: number;
      failed: number;
      crashLoopBackOff: number;
    };
    deployments: {
      available: number;
      unavailable: number;
    };
    events: {
      warningsLastHour: number;
    };
  };
};

type Namespace = {
  name: string;
};

type Pod = {
  name: string;
  namespace: string;
  phase: string;
  nodeName: string | null;
  ready: boolean;
  readyContainers: number;
  totalContainers: number;
  restarts: number;
  waitingReason: string | null;
};

type Deployment = {
  name: string;
  namespace: string;
  desiredReplicas: number;
  availableReplicas: number;
  readyReplicas: number;
  updatedReplicas: number;
  available: boolean;
};

type Service = {
  name: string;
  namespace: string;
  type: string;
  clusterIP: string;
  externalIPs: string[];
  ports: Array<{ name: string | null; port: number; targetPort: string }>;
};

type KubernetesEvent = {
  name: string;
  namespace: string;
  type: string;
  reason: string | null;
  message: string | null;
  lastTimestamp: string | null;
  involvedObject: { kind: string; name: string; namespace: string | null } | null;
};

type NamedResource = {
  name: string;
  namespace: string;
  [key: string]: string | number | boolean | null | string[] | undefined;
};

type Workloads = {
  statefulSets: NamedResource[];
  daemonSets: NamedResource[];
};

type MetricsSummary = {
  provider: string;
  status: 'available' | 'unavailable';
  reason?: string;
  topCpuPods?: Array<{ name: string; namespace: string; cpuMillicores: number; memoryMiB: number }>;
  topMemoryPods?: Array<{ name: string; namespace: string; cpuMillicores: number; memoryMiB: number }>;
};

type Finding = {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  resourceKind: string;
  resourceName: string;
  namespace: string | null;
  summary: string;
  evidence: string[];
  recommendation: string;
};

type AiIssue = {
  title: string;
  severity: 'info' | 'warning' | 'critical';
  resources: string[];
  evidence: string[];
  hypotheses: string[];
  recommendedNextSteps?: string[];
  readOnlyCommands?: string[];
  confidence: 'low' | 'medium' | 'high';
};

type AiAnalysis = {
  summary: string;
  overallSeverity: 'healthy' | 'info' | 'warning' | 'critical';
  prioritizedIssues: AiIssue[];
  missingData: string[];
  safeToIgnore: string[];
};

type AiAnalyzeResponse = {
  provider: string;
  analysis: AiAnalysis;
  toolsUsed?: Array<{ tool: string; status: string; params: Record<string, unknown> }>;
  cached?: boolean;
};

type ChatAnswer = {
  answer: string;
  confidence: 'low' | 'medium' | 'high';
  evidence: string[];
  readOnlyCommands?: string[];
  missingData: string[];
};

type ChatResponse = {
  provider: string;
  answer: ChatAnswer;
  toolsUsed: Array<{ tool: string; status: string; params: Record<string, unknown> }>;
  agentMetrics?: {
    cycles: number;
    toolsExecuted: string[];
    inputTokens: number;
    outputTokens: number;
    durationMs: number;
    provider: string;
    model: string;
    estimatedCost: number;
    finishReason: string;
  };
  cached?: boolean;
};

type AiStatus = {
  provider: string;
};

type SeverityFilter = 'all' | Finding['severity'];
type Theme = 'dark' | 'light';

type AuthState = {
  enabled: boolean;
  authenticated: boolean;
  username: string | null;
  oidcEnabled: boolean;
  localLoginEnabled?: boolean;
};

function normalizeAuthState(authState: AuthState): AuthState {
  return {
    ...authState,
    localLoginEnabled: authState.localLoginEnabled ?? true,
  };
}

function toneFor(value: number, warning = 1) {
  return value >= warning ? 'warn' : 'good';
}

function statusClass(pod: Pod) {
  if (pod.phase === 'Failed' || pod.waitingReason === 'CrashLoopBackOff') return 'bad';
  if (pod.phase === 'Pending' || pod.waitingReason || !pod.ready) return 'warn';
  return 'good';
}

export function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [summary, setSummary] = useState<ClusterSummary | null>(null);
  const [namespaces, setNamespaces] = useState<Namespace[]>([]);
  const [pods, setPods] = useState<Pod[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [events, setEvents] = useState<KubernetesEvent[]>([]);
  const [workloads, setWorkloads] = useState<Workloads>({ statefulSets: [], daemonSets: [] });
  const [jobs, setJobs] = useState<NamedResource[]>([]);
  const [pvcs, setPvcs] = useState<NamedResource[]>([]);
  const [ingresses, setIngresses] = useState<NamedResource[]>([]);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [selectedNamespace, setSelectedNamespace] = useState('all');
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [aiAnalysis, setAiAnalysis] = useState<AiAnalyzeResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [chatQuestion, setChatQuestion] = useState('');
  const [chatResponse, setChatResponse] = useState<ChatResponse | null>(null);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState('analysis');
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === 'undefined') return 'dark';
    const storedTheme = window.localStorage.getItem('koi-theme');
    if (storedTheme === 'light' || storedTheme === 'dark') return storedTheme;
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('koi-theme', theme);
  }, [theme]);

  useEffect(() => {
    async function loadAuth() {
      try {
        const response = await fetch(`${apiBaseUrl}/auth/me`, { credentials: 'include' });
        if (response.ok) {
          setAuth(normalizeAuthState((await response.json()) as AuthState));
          return;
        }
        setAuth({ enabled: true, authenticated: false, username: null, oidcEnabled: false, localLoginEnabled: true });
      } catch {
        setAuth({ enabled: true, authenticated: false, username: null, oidcEnabled: false, localLoginEnabled: true });
      }
    }
    void loadAuth();
  }, []);

  useEffect(() => {
    const sectionIds = ['analysis', 'dashboard', 'workloads', 'findings', 'events'];
    function updateActiveSection() {
      const current = sectionIds
        .map((id) => ({ id, top: document.getElementById(id)?.getBoundingClientRect().top ?? Number.POSITIVE_INFINITY }))
        .filter((section) => section.top <= 120)
        .at(-1);
      setActiveSection(current?.id ?? sectionIds[0]);
    }
    updateActiveSection();
    window.addEventListener('scroll', updateActiveSection, { passive: true });
    window.addEventListener('resize', updateActiveSection);
    return () => {
      window.removeEventListener('scroll', updateActiveSection);
      window.removeEventListener('resize', updateActiveSection);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadDashboard() {
      if (!auth) return;
      if (auth?.enabled && !auth.authenticated) return;
      try {
        const namespaceQuery = selectedNamespace === 'all' ? '' : `?namespace=${selectedNamespace}`;
        const [
          summaryResponse,
          findingsResponse,
          namespacesResponse,
          podsResponse,
          deploymentsResponse,
          servicesResponse,
          eventsResponse,
          workloadsResponse,
          jobsResponse,
          pvcsResponse,
          ingressesResponse,
          metricsResponse,
          aiStatusResponse,
        ] = await Promise.all([
          fetch(`${apiBaseUrl}/cluster/summary`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/findings`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/namespaces`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/pods${namespaceQuery}`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/deployments${namespaceQuery}`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/services${namespaceQuery}`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/events${namespaceQuery}${namespaceQuery ? '&' : '?'}limit=20&minutes=60`, {
            signal: controller.signal,
            credentials: 'include',
          }),
          fetch(`${apiBaseUrl}/workloads${namespaceQuery}`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/jobs${namespaceQuery}`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/pvcs${namespaceQuery}`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/ingresses${namespaceQuery}`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/metrics/summary`, { signal: controller.signal, credentials: 'include' }),
          fetch(`${apiBaseUrl}/ai/status`, { signal: controller.signal, credentials: 'include' }),
        ]);

        for (const response of [
          summaryResponse,
          findingsResponse,
          namespacesResponse,
          podsResponse,
          deploymentsResponse,
          servicesResponse,
          eventsResponse,
          workloadsResponse,
          jobsResponse,
          pvcsResponse,
          ingressesResponse,
          metricsResponse,
          aiStatusResponse,
        ]) {
          if (response.status === 401) {
            setAuth({ enabled: true, authenticated: false, username: null, oidcEnabled: auth?.oidcEnabled ?? false, localLoginEnabled: auth?.localLoginEnabled ?? true });
            return;
          }
          if (!response.ok) {
            throw new Error(`${response.url} returned ${response.status}`);
          }
        }

        setSummary((await summaryResponse.json()) as ClusterSummary);
        setFindings((await findingsResponse.json()) as Finding[]);
        setNamespaces((await namespacesResponse.json()) as Namespace[]);
        setPods((await podsResponse.json()) as Pod[]);
        setDeployments((await deploymentsResponse.json()) as Deployment[]);
        setServices((await servicesResponse.json()) as Service[]);
        setEvents((await eventsResponse.json()) as KubernetesEvent[]);
        setWorkloads((await workloadsResponse.json()) as Workloads);
        setJobs((await jobsResponse.json()) as NamedResource[]);
        setPvcs((await pvcsResponse.json()) as NamedResource[]);
        setIngresses((await ingressesResponse.json()) as NamedResource[]);
        setMetrics((await metricsResponse.json()) as MetricsSummary);
        setAiStatus((await aiStatusResponse.json()) as AiStatus);
        setError(null);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : 'Unable to load dashboard data');
        }
      }
    }

    void loadDashboard();
    const intervalId = window.setInterval(loadDashboard, 30_000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [auth, selectedNamespace, refreshCount]);

  async function login() {
    setLoginLoading(true);
    setLoginError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username: loginUsername.trim(), password: loginPassword.trim() }),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(errorPayload?.detail ?? 'Usuario o contraseña inválidos');
      }
      const nextAuth = (await response.json()) as { authenticated: boolean; username: string };
      setAuth({ enabled: true, authenticated: nextAuth.authenticated, username: nextAuth.username, oidcEnabled: auth?.oidcEnabled ?? false, localLoginEnabled: auth?.localLoginEnabled ?? true });
      setLoginPassword('');
      setRefreshCount((current) => current + 1);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : 'No se pudo iniciar sesión');
    } finally {
      setLoginLoading(false);
    }
  }

  async function logout() {
    await fetch(`${apiBaseUrl}/auth/logout`, { method: 'POST', credentials: 'include' });
    setAuth((current) => current ? { ...current, authenticated: false, username: null } : current);
  }

  function loginWithOidc() {
    window.location.href = `${apiBaseUrl}/auth/oidc/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  }

  const visibleFindings = findings.filter((finding) => {
    const matchesNamespace = selectedNamespace === 'all' || finding.namespace === selectedNamespace;
    const matchesSeverity = severityFilter === 'all' || finding.severity === severityFilter;
    return matchesNamespace && matchesSeverity;
  });

  async function analyzeWithAi() {
    setAiLoading(true);
    setAiError(null);
    try {
      const namespaceQuery = selectedNamespace === 'all' ? '' : `?namespace=${selectedNamespace}`;
      const response = await fetch(`${apiBaseUrl}/ai/analyze${namespaceQuery}`, { method: 'POST', credentials: 'include' });
      if (!response.ok) {
        throw new Error(`AI analyze returned ${response.status}`);
      }
      setAiAnalysis((await response.json()) as AiAnalyzeResponse);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : 'Unable to run AI analysis');
    } finally {
      setAiLoading(false);
    }
  }

  async function askAiChat() {
    if (!chatQuestion.trim()) return;
    setChatLoading(true);
    setChatError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          question: chatQuestion,
          namespace: selectedNamespace === 'all' ? null : selectedNamespace,
        }),
      });
      if (!response.ok) {
        throw new Error(`Chat returned ${response.status}`);
      }
      setChatResponse((await response.json()) as ChatResponse);
    } catch (err) {
      setChatError(err instanceof Error ? err.message : 'Unable to ask AI');
    } finally {
      setChatLoading(false);
    }
  }

  const cards = summary
    ? [
        {
          label: 'Cluster status',
          value: summary.cluster.status,
          tone: summary.cluster.status === 'healthy' ? 'good' : 'warn',
        },
        {
          label: 'Nodes ready',
          value: `${summary.cluster.readyNodes} / ${summary.cluster.nodes}`,
          tone: summary.cluster.readyNodes === summary.cluster.nodes ? 'good' : 'bad',
        },
        { label: 'Namespaces', value: summary.cluster.namespaces.toString(), tone: 'good' },
        { label: 'Pods running', value: summary.cluster.pods.running.toString(), tone: 'good' },
        {
          label: 'Pods pending',
          value: summary.cluster.pods.pending.toString(),
          tone: toneFor(summary.cluster.pods.pending),
        },
        {
          label: 'CrashLoopBackOff',
          value: summary.cluster.pods.crashLoopBackOff.toString(),
          tone: summary.cluster.pods.crashLoopBackOff > 0 ? 'bad' : 'good',
        },
        {
          label: 'Deployments unavailable',
          value: summary.cluster.deployments.unavailable.toString(),
          tone: summary.cluster.deployments.unavailable > 0 ? 'warn' : 'good',
        },
        {
          label: 'Warning events',
          value: summary.cluster.events.warningsLastHour.toString(),
          tone: toneFor(summary.cluster.events.warningsLastHour),
        },
      ]
    : [];
  const criticalFindings = visibleFindings.filter((finding) => finding.severity === 'critical').length;
  const warningFindings = visibleFindings.filter((finding) => finding.severity === 'warning').length;
  const impactedWorkloads = pods.filter((pod) => statusClass(pod) !== 'good').length + deployments.filter((deployment) => !deployment.available).length;
  const warningEvents = events.filter((event) => event.type === 'Warning');
  const activeProvider = chatResponse?.provider ?? aiAnalysis?.provider ?? aiStatus?.provider ?? 'bedrock';
  const activeInvestigation = chatResponse?.toolsUsed ?? aiAnalysis?.toolsUsed ?? [];
  const chatAgentTools = chatResponse?.agentMetrics?.toolsExecuted.length
    ? chatResponse.agentMetrics.toolsExecuted
    : chatResponse?.toolsUsed.map((tool) => tool.tool) ?? [];

  if (!auth) {
    return (
      <main className="login-page">
        <section className="login-brand-panel">
          <div className="brand login-brand">
            <span>KOI</span>
            <strong>KubeOps Insight</strong>
          </div>
          <h1>Operational intelligence for Kubernetes</h1>
          <p>Verificando la sesión antes de cargar la consola operacional.</p>
        </section>
        <section className="login-form-panel">
          <div className="login-card">
            <p className="eyebrow">Control de acceso</p>
            <h1>Verificando acceso</h1>
            <p>Validando credenciales y configuración de autenticación.</p>
          </div>
        </section>
      </main>
    );
  }

  if (auth.enabled && !auth.authenticated) {
    return (
      <main className="login-page">
        <section className="login-brand-panel">
          <div className="brand login-brand">
            <span>KOI</span>
            <strong>KubeOps Insight</strong>
          </div>
          <h1>Secure Kubernetes operations console</h1>
          <p>Accedé a diagnósticos, señales operacionales y análisis read-only con una sesión autenticada.</p>
        </section>
        <section className="login-form-panel">
          <div className="login-card">
            <p className="eyebrow">Control de acceso</p>
            <h1>Acceso requerido</h1>
            <p>{auth.oidcEnabled ? 'Ingresá con tu proveedor de identidad para continuar.' : 'Ingresá con tus credenciales para continuar.'}</p>
            {auth.oidcEnabled ? (
              <button type="button" onClick={loginWithOidc}>Ingresar con SSO</button>
            ) : null}
            {auth.localLoginEnabled ? (
              <>
                {auth.oidcEnabled ? <div className="login-divider">o usar credenciales locales</div> : null}
                <label>
                  Usuario
                  <input value={loginUsername} onChange={(event) => setLoginUsername(event.target.value)} autoComplete="username" />
                </label>
                <label>
                  Contraseña
                  <input value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} type="password" autoComplete="current-password" />
                </label>
                {loginError ? <div className="alert">{loginError}</div> : null}
                <button type="button" onClick={() => void login()} disabled={loginLoading}>
                  {loginLoading ? 'Ingresando...' : 'Ingresar'}
                </button>
              </>
            ) : null}
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span>KOI</span>
          <strong>KubeOps Insight</strong>
        </div>
        <nav>
          <a className={activeSection === 'analysis' ? 'active' : ''} href="#analysis" onClick={() => setActiveSection('analysis')}>Analysis</a>
          <a className={activeSection === 'dashboard' ? 'active' : ''} href="#dashboard" onClick={() => setActiveSection('dashboard')}>Signals</a>
          <a className={activeSection === 'workloads' ? 'active' : ''} href="#workloads" onClick={() => setActiveSection('workloads')}>Workloads</a>
          <a className={activeSection === 'findings' ? 'active' : ''} href="#findings" onClick={() => setActiveSection('findings')}>Diagnostics</a>
          <a className={activeSection === 'events' ? 'active' : ''} href="#events" onClick={() => setActiveSection('events')}>Events</a>
        </nav>
        {auth?.enabled && auth.authenticated ? (
          <div className="sidebar-session">
            <span>Signed in as</span>
            <strong>{auth.username}</strong>
            <button type="button" className="logout-button" onClick={() => void logout()}>
              Logout
            </button>
          </div>
        ) : null}
      </aside>

      <section className="content">
        <header className="header">
          <div>
            <p className="eyebrow">{summary ? `${summary.mode} cluster intelligence` : 'Loading cluster intelligence'}</p>
            <h1>Operations Command Center</h1>
            <p className="header-copy">Operational analysis grounded in live Kubernetes API evidence and deterministic diagnostics.</p>
          </div>
          <div className="header-status">
            <span>API</span>
            <strong>{apiBaseUrl}</strong>
          </div>
        </header>

        <section className="toolbar command-toolbar" aria-label="Dashboard filters">
          <label>
            Scope
            <select value={selectedNamespace} onChange={(event) => setSelectedNamespace(event.target.value)}>
              <option value="all">All namespaces</option>
              {namespaces.map((namespace) => (
                <option value={namespace.name} key={namespace.name}>{namespace.name}</option>
              ))}
            </select>
          </label>
          <label>
            Severity
            <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as SeverityFilter)}>
              <option value="all">All severities</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
          </label>
          <button type="button" onClick={() => setRefreshCount((current) => current + 1)}>
            Refresh
          </button>
          <button type="button" className="secondary-button" onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}>
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>
        </section>

        {error ? <div className="alert">Could not load dashboard data: {error}</div> : null}
        {!summary && !error ? <div className="panel state-panel">Loading cluster intelligence...</div> : null}

        {summary ? (
          <section className="executive-strip" aria-label="Executive signals">
            <article className={`signal-card ${criticalFindings > 0 ? 'bad' : 'good'}`}>
              <span>Critical Findings</span>
              <strong>{criticalFindings}</strong>
              <small>{warningFindings} warnings in current scope</small>
            </article>
            <article className={`signal-card ${impactedWorkloads > 0 ? 'warn' : 'good'}`}>
              <span>Impacted Workloads</span>
              <strong>{impactedWorkloads}</strong>
              <small>{pods.length} pods · {deployments.length} deployments observed</small>
            </article>
            <article className={`signal-card ${summary.cluster.events.warningsLastHour > 0 ? 'warn' : 'good'}`}>
              <span>Warnings Last Hour</span>
              <strong>{summary.cluster.events.warningsLastHour}</strong>
              <small>{warningEvents.length} warning events loaded</small>
            </article>
            <article className="signal-card info">
              <span>AI Status</span>
              <strong>{activeProvider}</strong>
              <small>{activeInvestigation.length} read-only checks executed</small>
            </article>
          </section>
        ) : null}

        <section className="panel ai-panel command-panel" id="analysis">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Análisis del cluster</p>
              <h2>Investigación guiada con evidencia Kubernetes</h2>
            </div>
            <button type="button" onClick={() => void analyzeWithAi()} disabled={aiLoading}>
              {aiLoading ? 'Analizando...' : 'Analizar vista actual'}
            </button>
          </div>

          <p>
            La app consulta la API de Kubernetes, recopila contexto acotado y entrega un diagnóstico accionable sin pedirle al operador que ejecute comandos adicionales.
          </p>

          <div className="runtime-strip">
            <span className="runtime-chip">Provider {activeProvider}</span>
            <span className="runtime-chip">Scope {selectedNamespace === 'all' ? 'cluster' : selectedNamespace}</span>
            <span className="runtime-chip">Cache {chatResponse?.cached || aiAnalysis?.cached ? 'hit' : 'ready'}</span>
          </div>

          <div className="analysis-grid">
            <div className="chat-box">
              <label>
                Consulta de investigación
                <textarea
                  value={chatQuestion}
                  onChange={(event) => setChatQuestion(event.target.value)}
                  placeholder="Ej: Revisá los pods con errores, eventos recientes y PVCs pendientes en este namespace."
                  rows={3}
                />
              </label>
              <button type="button" onClick={() => void askAiChat()} disabled={chatLoading}>
                {chatLoading ? 'Investigando...' : 'Run analysis'}
              </button>
            </div>
            <aside className="context-card">
              <span>Current Scope</span>
              <strong>{selectedNamespace === 'all' ? 'All namespaces' : selectedNamespace}</strong>
              <p>{visibleFindings.length} deterministic findings · {events.length} events · {metrics?.status ?? 'metrics loading'}</p>
            </aside>
          </div>

          {chatError ? <div className="alert">No se pudo ejecutar el chat AI: {chatError}</div> : null}
          {!chatResponse && !chatLoading ? (
            <div className="empty-state">No analysis run yet. Submit an investigation brief or analyze the current view.</div>
          ) : null}
          {chatResponse ? (
            <div className="ai-summary chat-answer">
              <div className="result-meta">
                <span className="runtime-chip">{chatResponse.cached ? 'cached response' : 'fresh response'}</span>
                <span className="runtime-chip">{chatResponse.toolsUsed.length} checks</span>
              </div>
              <p>{chatResponse.answer.answer}</p>
              <strong>Evidencia</strong>
              <p>{chatResponse.answer.evidence.join(' · ') || 'Sin evidencia adicional.'}</p>
              {chatResponse.answer.missingData.length > 0 ? (
                <>
                  <strong>Datos faltantes</strong>
                  <p>{chatResponse.answer.missingData.join(' · ')}</p>
                </>
              ) : null}
              {chatResponse.toolsUsed.length > 0 ? (
                <>
                  <strong>Investigación read-only ejecutada</strong>
                  <p>{chatResponse.toolsUsed.map((tool) => `${tool.tool}(${tool.status})`).join(' · ')}</p>
                </>
              ) : null}
              {chatResponse.agentMetrics ? (
                <div className="agent-metrics">
                  <strong>
                    Agent: {chatResponse.agentMetrics.finishReason} · {chatResponse.agentMetrics.cycles} cycles ·{' '}
                    {(chatResponse.agentMetrics.durationMs / 1000).toFixed(1)}s · ${chatResponse.agentMetrics.estimatedCost} ·{' '}
                    {chatAgentTools.length} tools
                  </strong>
                  <p>Tools: {chatAgentTools.join(' -> ') || 'none'}</p>
                  <small>
                    Tokens: {chatResponse.agentMetrics.inputTokens} input / {chatResponse.agentMetrics.outputTokens} output · Model:{' '}
                    {chatResponse.agentMetrics.model}
                  </small>
                </div>
              ) : (
                <small>Provider: {chatResponse.provider} · Cached: {String(chatResponse.cached ?? false)}</small>
              )}
            </div>
          ) : null}

          {aiError ? <div className="alert">No se pudo ejecutar el análisis AI: {aiError}</div> : null}
          {aiAnalysis ? (
            <div className="ai-result">
              <div className="ai-summary">
                <span className={`badge ${aiAnalysis.analysis.overallSeverity === 'healthy' ? 'info' : aiAnalysis.analysis.overallSeverity}`}>
                  {aiAnalysis.analysis.overallSeverity}
                </span>
                <span className="runtime-chip">{aiAnalysis.cached ? 'cached response' : 'fresh response'}</span>
                <p>{aiAnalysis.analysis.summary}</p>
                <small>
                  Provider: {aiAnalysis.provider} · Cached:{' '}
                  {String(aiAnalysis.cached ?? false)}
                </small>
                {aiAnalysis.toolsUsed && aiAnalysis.toolsUsed.length > 0 ? (
                  <p className="investigation-trace">
                    Investigación ejecutada: {aiAnalysis.toolsUsed.map((tool) => `${tool.tool}(${tool.status})`).join(' · ')}
                  </p>
                ) : null}
              </div>

              <div className="findings-list">
                {aiAnalysis.analysis.prioritizedIssues.length === 0 ? (
                  <div className="empty-state">No AI-prioritized issues returned for this scope.</div>
                ) : null}
                {aiAnalysis.analysis.prioritizedIssues.map((issue) => (
                  <article className={`finding ${issue.severity}`} key={`${issue.severity}-${issue.title}`}>
                    <div>
                      <span className={`badge ${issue.severity}`}>{issue.severity}</span>
                      <h3>{issue.title}</h3>
                      <p>{issue.resources.join(', ')}</p>
                    </div>
                    <div>
                      <strong>Evidencia</strong>
                      <p>{issue.evidence.join(' · ')}</p>
                      <strong>Diagnóstico</strong>
                      <p>{issue.hypotheses.join(' · ')}</p>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          ) : null}
        </section>

        {summary ? (
          <>
          <section className="section-title" id="dashboard">
            <p className="eyebrow">Signals</p>
            <h2>Cluster signals</h2>
          </section>
          <section className="grid signal-grid" aria-label="Cluster summary">
            {cards.map((card) => (
              <article className={`card ${card.tone}`} key={card.label}>
                <span>{card.label}</span>
                <strong>{card.value}</strong>
              </article>
            ))}
          </section>
          </>
        ) : null}

        <section className="section-title" id="workloads">
          <p className="eyebrow">Operational evidence</p>
          <h2>Cluster resources</h2>
        </section>

        <section className="panel" id="pods">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Workloads</p>
              <h2>Pods</h2>
            </div>
            <span className="status">{pods.length} pods</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Namespace</th>
                  <th>Phase</th>
                  <th>Ready</th>
                  <th>Restarts</th>
                  <th>Node</th>
                </tr>
              </thead>
              <tbody>
                {pods.map((pod) => (
                  <tr key={`${pod.namespace}-${pod.name}`}>
                    <td>{pod.name}</td>
                    <td>{pod.namespace}</td>
                    <td><span className={`pill ${statusClass(pod)}`}>{pod.waitingReason ?? pod.phase}</span></td>
                    <td>{pod.readyContainers}/{pod.totalContainers}</td>
                    <td>{pod.restarts}</td>
                    <td>{pod.nodeName ?? 'unscheduled'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel split-panel">
          <div>
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Workloads</p>
                <h2>Deployments</h2>
              </div>
              <span className="status">{deployments.length} deployments</span>
            </div>
            <div className="table-wrap compact">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Namespace</th>
                    <th>Ready</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {deployments.map((deployment) => (
                    <tr key={`${deployment.namespace}-${deployment.name}`}>
                      <td>{deployment.name}</td>
                      <td>{deployment.namespace}</td>
                      <td>
                        <span className={`pill ${deployment.available ? 'good' : 'warn'}`}>
                          {deployment.availableReplicas}/{deployment.desiredReplicas}
                        </span>
                      </td>
                      <td>{deployment.updatedReplicas}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Networking</p>
                <h2>Services</h2>
              </div>
              <span className="status">{services.length} services</span>
            </div>
            <div className="table-wrap compact">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Namespace</th>
                    <th>Type</th>
                    <th>Ports</th>
                  </tr>
                </thead>
                <tbody>
                  {services.map((service) => (
                    <tr key={`${service.namespace}-${service.name}`}>
                      <td>{service.name}</td>
                      <td>{service.namespace}</td>
                      <td>{service.type}</td>
                      <td>{service.ports.map((port) => `${port.port}:${port.targetPort}`).join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="panel split-panel">
          <div>
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Workloads</p>
                <h2>StatefulSets / DaemonSets / Jobs</h2>
              </div>
              <span className="status">
                {workloads.statefulSets.length + workloads.daemonSets.length + jobs.length} resources
              </span>
            </div>
            <div className="resource-list">
              {[...workloads.statefulSets, ...workloads.daemonSets, ...jobs].slice(0, 10).map((resource) => (
                <p key={`${resource.namespace}-${resource.name}`}>
                  {resource.namespace}/{resource.name}
                </p>
              ))}
            </div>
          </div>

          <div>
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Storage / Network</p>
                <h2>PVCs / Ingresses</h2>
              </div>
              <span className="status">{pvcs.length + ingresses.length} resources</span>
            </div>
            <div className="resource-list">
              {[...pvcs, ...ingresses].slice(0, 10).map((resource) => (
                <p key={`${resource.namespace}-${resource.name}`}>
                  {resource.namespace}/{resource.name}
                </p>
              ))}
            </div>
          </div>
        </section>

        <section className="panel findings-panel" id="findings">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Diagnostics</p>
              <h2>Detected Issues</h2>
            </div>
            <span className="status">{visibleFindings.length} findings</span>
          </div>

          {visibleFindings.length === 0 ? (
            <div className="empty-state">No deterministic issues detected for the current filters.</div>
          ) : (
            <div className="findings-list">
              {visibleFindings.slice(0, 8).map((finding) => (
                <article className={`finding ${finding.severity}`} key={finding.id}>
                  <div>
                    <span className={`badge ${finding.severity}`}>{finding.severity}</span>
                    <h3>{finding.summary}</h3>
                    <p>
                      {finding.resourceKind}/{finding.resourceName}
                      {finding.namespace ? ` in ${finding.namespace}` : ''}
                    </p>
                  </div>
                  <div>
                    <strong>Evidence</strong>
                    <p>{finding.evidence.join(' · ')}</p>
                    <strong>Recommendation</strong>
                    <p>{finding.recommendation}</p>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="panel meta-panel" id="events">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Recent</p>
              <h2>Warning Events</h2>
            </div>
            <span className="status">{events.length} events</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Reason</th>
                  <th>Object</th>
                  <th>Namespace</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {events.filter((event) => event.type === 'Warning').map((event) => (
                  <tr key={`${event.namespace}-${event.name}`}>
                    <td>{event.reason ?? 'Warning'}</td>
                    <td>{event.involvedObject ? `${event.involvedObject.kind}/${event.involvedObject.name}` : event.name}</td>
                    <td>{event.namespace}</td>
                    <td>{event.message ?? 'No message'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel meta-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Metrics</p>
              <h2>Metrics Server</h2>
            </div>
            <span className={`pill ${metrics?.status === 'available' ? 'good' : 'warn'}`}>
              {metrics?.status ?? 'loading'}
            </span>
          </div>
          {metrics?.status === 'available' ? (
            <div className="split-panel nested">
              <div>
                <h3>Top CPU Pods</h3>
                {(metrics.topCpuPods ?? []).map((pod) => (
                  <p key={`${pod.namespace}-${pod.name}-cpu`}>
                    {pod.namespace}/{pod.name}: {pod.cpuMillicores}m
                  </p>
                ))}
              </div>
              <div>
                <h3>Top Memory Pods</h3>
                {(metrics.topMemoryPods ?? []).map((pod) => (
                  <p key={`${pod.namespace}-${pod.name}-mem`}>
                    {pod.namespace}/{pod.name}: {pod.memoryMiB}Mi
                  </p>
                ))}
              </div>
            </div>
          ) : (
            <p>{metrics?.reason ?? 'Metrics API status is loading.'}</p>
          )}
        </section>

        <section className="panel meta-panel">
          <p className="eyebrow">Runtime</p>
          <h2>{summary?.source ?? 'Kubernetes API'} summary</h2>
          <p>The dashboard refreshes every 30 seconds. AI calls are manual, cached, and backed by read-only Kubernetes evidence.</p>
          {summary?.timestamp ? <p>Last update: {new Date(summary.timestamp).toLocaleString()}</p> : null}
        </section>
      </section>
    </main>
  );
}
