import Dashboard from "./components/Dashboard.jsx";

export default function AppView() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <h1>GridOS-Logic v2.0</h1>
        <p>
          Autonomous perch routing with dynamic harmonics, self-adapting memory,
          and mandatory human-command authority.
        </p>
      </header>
      <Dashboard />
    </main>
  );
}
