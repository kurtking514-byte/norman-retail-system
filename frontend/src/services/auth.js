import api from './api';

const TOKEN_KEY = 'norman_admin_token';

export async function login(username, password) {
  try {
    const response = await api.post('/auth/login', { username, password });
    const token = response.data.access_token;
    localStorage.setItem(TOKEN_KEY, token);
    return token;
  } catch (error) {
    // Parse the backend's { success: false, error: { message } } shape
    if (error.response && error.response.data) {
      const data = error.response.data;
      if (data.error && data.error.message) {
        throw new Error(data.error.message);
      }
      if (data.detail && data.detail.error && data.detail.error.message) {
        throw new Error(data.detail.error.message);
      }
      throw new Error('Login failed. Please check your credentials.');
    }
    throw new Error('Network error. Please try again.');
  }
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function isAuthenticated() {
  return !!getToken();
}
