import { Component, lazy, Suspense, useState, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import StatusBar from "./components/StatusBar";
const EvaluationPage = lazy(() => import("./pages/EvaluationPage"));
const ExplorePage = lazy(() => import("./pages/ExplorePage"));
const IncidentsPage = lazy(() => import("./pages/IncidentsPage"));
const LivePage = lazy(() => import("./pages/LivePage"));
const RulesPage = lazy(() => import("./pages/RulesPage"));
const SessionPage = lazy(() => import("./pages/SessionPage"));
const SessionsPage = lazy(() => import("./pages/SessionsPage"));
import { useSource, withSource } from "./source";

class RouteBoundary extends Component<{children: ReactNode}, {error: boolean}> {
  state = {error: false};
  static getDerivedStateFromError() { return {error: true}; }
  render() {
    return this.state.error ? <div className="banner" role="alert">This page could not load. <button onClick={() => window.location.reload()}>Reload dashboard</button></div> : this.props.children;
  }
}

const NAV: [string, string][] = [
  ["/live", "Live"],
  ["/sessions", "Sessions"],
  ["/incidents", "Incidents"],
  ["/explore", "Explore"],
  ["/evaluation", "Evaluation"],
  ["/rules", "Rules"],
];

export default function App() {
  const [source, setSource] = useSource();
  const [navOpen, setNavOpen] = useState(false);
  return (
    <div className="app">
      <StatusBar source={source} onSourceChange={setSource} />
      <button className="nav-toggle" aria-expanded={navOpen} aria-controls="page-navigation" onClick={() => setNavOpen(!navOpen)}>Pages {navOpen ? "−" : "+"}</button>
      <nav id="page-navigation" aria-label="Pages" className={`tabs ${navOpen ? "open" : ""}`}>
        {NAV.map(([path, label]) => (
          <NavLink onClick={() => setNavOpen(false)} key={path} to={withSource(path, source)} className={({ isActive }) => (isActive ? "tab active" : "tab")}>
            {label}
          </NavLink>
        ))}
      </nav>
      <main>
        <RouteBoundary><Suspense fallback={<p className="muted" role="status">Loading page…</p>}><Routes>
          <Route path="/" element={<Navigate to={withSource("/live", source)} replace />} />
          <Route path="/live" element={<LivePage source={source} />} />
          <Route path="/sessions" element={<SessionsPage source={source} />} />
          <Route path="/sessions/:agent/:sessionId" element={<SessionPage source={source} />} />
          <Route path="/incidents" element={<IncidentsPage source={source} />} />
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/rules" element={<RulesPage />} />
          <Route path="*" element={<p className="empty">Page not found.</p>} />
        </Routes></Suspense></RouteBoundary>
      </main>
    </div>
  );
}
