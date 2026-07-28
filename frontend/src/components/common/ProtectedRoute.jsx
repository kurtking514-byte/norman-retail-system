import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    // Redirect to /login preserving the attempted URL for post-login redirect
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}
