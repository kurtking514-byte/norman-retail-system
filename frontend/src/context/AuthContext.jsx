import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { login as authLogin, logout as authLogout, getToken, isAuthenticated } from '../services/auth';

const AuthContext = createContext(null);

// The token has a "sub" claim containing the username
function decodeUsername(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.sub || 'Admin';
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  // Restore the session synchronously so protected routes don't redirect to
  // /login on a page refresh before the stored token has been read.
  const [token, setToken] = useState(() => {
    const storedToken = getToken();
    return storedToken && decodeUsername(storedToken) ? storedToken : null;
  });
  const [user, setUser] = useState(() => (token ? { username: decodeUsername(token) } : null));

  useEffect(() => {
    if (!token && getToken()) {
      // Stored token was malformed — clear it
      authLogout();
    }
  }, [token]);

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
