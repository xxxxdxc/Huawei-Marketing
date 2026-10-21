import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './style.css';
const root = createRoot(document.getElementById('root')!);
const preview = import.meta.env.DEV ? new URLSearchParams(location.search).get('preview') : null;
if (preview === 'planner-v3') {
  import('./SelectionPreview').then(({ default: Preview }) => root.render(<React.StrictMode><Preview /></React.StrictMode>)).catch(() => root.render(<p role="alert">演示页未能载入，请刷新后重试。</p>));
} else if (preview === 'planner-v2') {
  import('./PlannerPreview').then(({ default: Preview }) => root.render(<React.StrictMode><Preview /></React.StrictMode>)).catch(() => root.render(<p role="alert">演示页未能载入，请刷新后重试。</p>));
} else {
  root.render(<React.StrictMode><App /></React.StrictMode>);
}
