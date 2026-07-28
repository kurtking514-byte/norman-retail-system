import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { login as authLogin, logout as authLogout, getToken, isAuthenticated } from '../services/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);

  // On mount, restore session from localStorage if a token exists
  useEffect(() => {
    const storedToken = getToken();
    if (storedToken) {
      setToken(storedToken);
      // The token has a "sub" claim containing the username
      try {
        const payload = JSON.parse(atob(storedToken.split('.')[1]));
        setUser({ username: payload.sub || 'Admin' });
      } catch {
        // If token is malformed, clear it
        authLogout();
        setToken(null);
      }
    }
  }, []);

  const login = useCallback(async (username, password) => {
    const newToken = await authLogin(username, password);
    setToken(newToken);
    try {
      const payload = JSON.parse(atob(newToken.split('.')[1]));
      setUser({ username: payload.sub || username });
    } catch {
      setUser({ username });
    }
  }, []);

  const logout = useCallback(() => {
    authLogout();
    setToken(null);
    setUser(null);
  }, []);

  const value = {
    user,
    token,
    login,
    logout,
    isAuthenticated: !!token,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
