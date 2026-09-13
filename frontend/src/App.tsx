import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { initializeAuth } from './store/auth';
import { ProtectedRoute } from './components/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ResearchDeskPage from './pages/ResearchDeskPage';

export default function App() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    initializeAuth().finally(() => setReady(true));
  }, []);

  if (!ready) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ProtectedRoute><ResearchDeskPage /></ProtectedRoute>} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/dashboard" element={<Navigate to="/" replace />} />
        <Route path="/research" element={<Navigate to="/" replace />} />
        <Route path="/agent" element={<Navigate to="/?view=investor-ai" replace />} />
        <Route path="/risk" element={<Navigate to="/?view=info" replace />} />
        <Route path="/scenarios" element={<Navigate to="/" replace />} />
        <Route path="/compare" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
