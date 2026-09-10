import { useEffect } from 'react';
import { Route, Routes } from 'react-router-dom';
import { Login } from './pages/Login';
import { ProjectList } from './pages/ProjectList';
import { Quantification } from './pages/Quantification';
import { Register } from './pages/Register';
import { Viewer } from './pages/Viewer';
import { useAuthStore } from './store/useAuthStore';

function App() {
  const refresh = useAuthStore((s) => s.refresh);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <Routes>
      <Route path="/" element={<ProjectList />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/project/:projectId/viewer" element={<Viewer />} />
      <Route path="/project/:projectId/quantification" element={<Quantification />} />
    </Routes>
  );
}

export default App;
