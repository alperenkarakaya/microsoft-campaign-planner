import { create } from 'zustand';
import { authAPI } from '../lib/api';
import type { User } from '../lib/types';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  
  login: (email: string, password: string) => Promise<void>;
  register: (email:  string, username: string, password:  string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem('access_token'),
  isAuthenticated: !! localStorage.getItem('access_token'),
  isLoading: false,
  
  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const data = await authAPI.login(email, password);
      localStorage.setItem('access_token', data.access_token);
      
      const user = await authAPI.getMe();
      
      set({
        user,
        token: data.access_token,
        isAuthenticated: true,
        isLoading: false
      });
    } catch (error: any) {
      set({ isLoading: false });
      console.error('Login error:', error);
      console.error('Error response:', error.response?.data);
      throw error;
    }
  },
  
  register: async (email, username, password) => {
    set({ isLoading:  true });
    try {
      await authAPI.register(email, username, password);
      // Register sonrası otomatik login
      await useAuthStore.getState().login(email, password);
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },
  
  logout: () => {
    localStorage. removeItem('access_token');
    set({
      user: null,
      token: null,
      isAuthenticated: false
    });
  },
  
  checkAuth: async () => {
    const token = localStorage.getItem('access_token');
    if (! token) {
      set({ isAuthenticated: false });
      return;
    }
    
    try {
      const user = await authAPI.getMe();
      set({ user, isAuthenticated: true });
    } catch (error) {
      localStorage.removeItem('access_token');
      set({ user: null, isAuthenticated: false });
    }
  }
}));