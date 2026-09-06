import { Route, Routes } from 'react-router-dom';
import { ProjectList } from './pages/ProjectList';
import { Quantification } from './pages/Quantification';
import { Viewer } from './pages/Viewer';

function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectList />} />
      <Route path="/project/:projectId/viewer" element={<Viewer />} />
      <Route path="/project/:projectId/quantification" element={<Quantification />} />
    </Routes>
  );
}

export default App;
