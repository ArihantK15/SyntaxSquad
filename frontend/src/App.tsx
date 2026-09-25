import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Navbar } from './components/Navbar';
import { PrivacyNotice } from './components/PrivacyNotice';
import { DashboardPage } from './pages/DashboardPage';
import { ScreeningPage } from './pages/ScreeningPage';
import { ReviewQueuePage } from './pages/ReviewQueuePage';
import { CasesListPage } from './pages/CasesListPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { AuditTrailPage } from './pages/AuditTrailPage';
import { SettingsPage } from './pages/SettingsPage';
import { CaseDetailPage } from './pages/CaseDetailPage';
import { ChangeDetectionPage } from './pages/ChangeDetectionPage';
import { ComplianceDashboardPage } from './pages/ComplianceDashboardPage';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<string>('dashboard');
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  const handleSelectCase = (caseId: string) => {
    setSelectedCaseId(caseId);
    setCurrentTab('detail');
  };

  const handleBackFromDetail = () => {
    setSelectedCaseId(null);
    setCurrentTab('dashboard');
  };

  const handleScenarioLoaded = (caseId: string) => {
    setSelectedCaseId(caseId);
    setCurrentTab('detail');
  };

  return (
    <div className="flex h-screen bg-[#070a12] text-graphite-100 overflow-hidden font-sans">
      {/* Sidebar */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={(tab) => {
          setSelectedCaseId(null);
          setCurrentTab(tab);
        }}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Navbar
          currentTab={currentTab}
          onScenarioLoaded={handleScenarioLoaded}
        />

        <main className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
          <PrivacyNotice />

          {currentTab === 'dashboard' && (
            <DashboardPage
              onSelectCase={handleSelectCase}
              onNavigateNewScreening={() => setCurrentTab('screening')}
              onNavigateQueue={() => setCurrentTab('queue')}
            />
          )}

          {currentTab === 'screening' && (
            <ScreeningPage onScreeningComplete={handleSelectCase} />
          )}

          {currentTab === 'queue' && (
            <ReviewQueuePage onSelectCase={handleSelectCase} />
          )}

          {currentTab === 'cases' && (
            <CasesListPage onSelectCase={handleSelectCase} />
          )}

          {currentTab === 'analytics' && (
            <AnalyticsPage />
          )}

          {currentTab === 'audit' && (
            <AuditTrailPage onSelectCase={handleSelectCase} />
          )}

          {currentTab === 'settings' && (
            <SettingsPage />
          )}

          {currentTab === 'change_detection' && (
            <ChangeDetectionPage />
          )}

          {currentTab === 'compliance' && (
            <ComplianceDashboardPage />
          )}

          {currentTab === 'detail' && selectedCaseId && (
            <CaseDetailPage
              caseId={selectedCaseId}
              onBack={handleBackFromDetail}
            />
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
