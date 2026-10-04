import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import { readToken } from './api.js';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App token={readToken()} />
  </StrictMode>,
);
