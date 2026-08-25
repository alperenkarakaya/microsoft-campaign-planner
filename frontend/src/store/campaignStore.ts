import { create } from 'zustand';
import { campaignsAPI } from '../lib/api';
import type { Campaign } from '../lib/types';

interface CampaignState {
  campaigns: Campaign[];
  selectedCampaign: Campaign | null;
  isLoading: boolean;
  
  fetchCampaigns: (status?: string) => Promise<void>;
  fetchCampaign: (id: number) => Promise<void>;
  createCampaign: (data: any) => Promise<void>;
  updateCampaign: (id:  number, data: any) => Promise<void>;
  deleteCampaign: (id: number) => Promise<void>;
}

export const useCampaignStore = create<CampaignState>((set) => ({
  campaigns: [],
  selectedCampaign: null,
  isLoading: false,
  
  fetchCampaigns:  async (status) => {
    set({ isLoading: true });
    try {
      const data = await campaignsAPI.list(status);
      set({ campaigns: data, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },
  
  fetchCampaign: async (id) => {
    set({ isLoading: true });
    try {
      const data = await campaignsAPI.get(id);
      set({ selectedCampaign: data, isLoading:  false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },
  
  createCampaign: async (data) => {
    set({ isLoading: true });
    try {
      await campaignsAPI.create(data);
      await useCampaignStore.getState().fetchCampaigns();
      set({ isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },
  
  updateCampaign: async (id, data) => {
    set({ isLoading: true });
    try {
      await campaignsAPI.update(id, data);
      await useCampaignStore.getState().fetchCampaigns();
      set({ isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },
  
  deleteCampaign: async (id) => {
    set({ isLoading: true });
    try {
      await campaignsAPI. delete(id);
      await useCampaignStore.getState().fetchCampaigns();
      set({ isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  }
}));