import { BrowserRouter, Routes, Route } from 'react-router-dom';
import DashboardLayout from './components/layout/DashboardLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Inventory from './pages/Inventory';
import Reservations from './pages/Reservations';
import Repairs from './pages/Repairs';
import LiveChat from './pages/LiveChat';
import ProtectedRoute from './components/common/ProtectedRoute';
import { Navigate } from 'react-router-dom';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Dashboard />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/inventory"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Inventory />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reservations"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Reservations />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/repairs"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Repairs />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/live-chat"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <LiveChat />
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
      {/* Default redirect */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
