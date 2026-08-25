import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Navbar } from './components/Navbar';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DashboardPage } from './pages/DashboardPage';
import { CampaignsPage } from './pages/CampaignsPage';
import { CampaignFormPage } from './pages/CampaignFormPage';
import { CampaignDetailPage } from './pages/CampaignDetailPage';
import { InfluencersPage } from './pages/InfluencersPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { BrandProfilesPage } from './pages/BrandProfilesPage';
import { BrandProfileFormPage } from './pages/BrandProfileFormPage';
import { InfluencerDiscoveryPage } from './pages/InfluencerDiscoveryPage';
import { RosterPage } from './pages/RosterPage';
import { CreatorDetailPage } from './pages/CreatorDetailPage';
import { CampaignIntelligencePage } from './pages/CampaignIntelligencePage';
import { ContentStudioPage } from './pages/ContentStudioPage';
import { AIAssistantPage } from './pages/AIAssistantPage';

import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div style={styles.app}>
        <Navbar />
        <main style={styles.main}>
          <ErrorBoundary>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            
            <Route
              path="/campaigns"
              element={
                <ProtectedRoute>
                  <CampaignsPage />
                </ProtectedRoute>
              }
            />
            
            <Route
              path="/campaigns/new"
              element={
                <ProtectedRoute>
                  <CampaignFormPage />
                </ProtectedRoute>
              }
            />
            
            <Route
              path="/campaigns/:id"
              element={
                <ProtectedRoute>
                  <CampaignDetailPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/campaigns/:id/intelligence"
              element={
                <ProtectedRoute>
                  <CampaignIntelligencePage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/content-studio"
              element={
                <ProtectedRoute>
                  <ContentStudioPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/assistant"
              element={
                <ProtectedRoute>
                  <AIAssistantPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/roster"
              element={
                <ProtectedRoute>
                  <RosterPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/roster/:creatorId"
              element={
                <ProtectedRoute>
                  <CreatorDetailPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/influencers"
              element={
                <ProtectedRoute>
                  <InfluencersPage />
                </ProtectedRoute>
              }
            />
            
            <Route
              path="/analytics"
              element={
                <ProtectedRoute>
                  <AnalyticsPage />
                </ProtectedRoute>
              }
            />
            
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route
              path="/brands"
              element={
                <ProtectedRoute>
                  <BrandProfilesPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/brands/new"
              element={
                <ProtectedRoute>
                  <BrandProfileFormPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/brands/:brandId/discover"
              element={
                <ProtectedRoute>
                  <InfluencerDiscoveryPage />
                </ProtectedRoute>
              }
            />
          </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </BrowserRouter>
  );
}

const styles = {
  app: {
    minHeight: '100vh',
    background: '#f5f7fa',
  },
  main: {
    minHeight: 'calc(100vh - 70px)',
  },
};




export default App;