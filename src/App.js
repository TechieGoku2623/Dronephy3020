import React from "react";
import Dashboard from "./components/Dashboard.jsx";

export default function App() {
  return React.createElement(
    "main",
    { className: "app-shell" },
    React.createElement(
      "header",
      { className: "app-header" },
      React.createElement("h1", null, "GridOS-Logic v2.0"),
      React.createElement(
        "p",
        null,
        "Autonomous perch routing with dynamic harmonics, self-adapting memory, and mandatory human-command authority.",
      ),
    ),
    React.createElement(Dashboard),
  );
}
