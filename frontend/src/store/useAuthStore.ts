import { create } from 'zustand';
import { api } from '../api/client';
import type { User } from '../api/types';

interface AuthState {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,

  refresh: async () => {
    const { user } = await api.me();
    set({ user, loading: false });
  },

  login: async (email, password) => {
    const user = await api.login(email, password);
    set({ user });
  },

  register: async (email, password) => {
    const user = await api.register(email, password);
    set({ user });
  },

  logout: async () => {
    await api.logout();
    set({ user: null });
  },
}));
