import React, { useState, useEffect } from 'react';
import './App.css';
import NavBar from './components/NavBar';
import LandingPage from './pages/LandingPage';
import ExplorerPage from './pages/ExplorerPage';
import ValidatorsPage from './pages/ValidatorsPage';
import InferencePage from './pages/InferencePage';
import NetworkPage from './pages/NetworkPage';
import AboutPage from './pages/AboutPage';
import ResearchPage from './pages/ResearchPage';
import NewsPage from './pages/NewsPage';
import PartnersPage from './pages/PartnersPage';
import GetStartedPage from './pages/GetStartedPage';
import JoinPage from './pages/JoinPage';
import WhitepaperPage from './pages/WhitepaperPage';

const PAGES = ['home', 'explorer', 'validators', 'inference', 'network', 'about', 'research', 'news', 'partners', 'get-started', 'join', 'whitepaper'];

// Read hash from window location (e.g. #explorer → 'explorer')
function getPage() {
  const h = window.location.hash.replace('#', '') || 'home';
  return PAGES.includes(h) ? h : 'home';
}

export default function App() {
  const [page, setPage] = useState(getPage);

  // Keep page in sync with browser hash (back/forward)
  useEffect(() => {
    const onHash = () => setPage(getPage());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const navigate = (p) => {
    window.location.hash = p === 'home' ? '' : p;
    setPage(p);
  };

  return (
    <div className="app-root">
      <NavBar current={page} navigate={navigate} />
      <main className="app-content">
        {page === 'home' && <LandingPage navigate={navigate} />}
        {page === 'explorer' && <ExplorerPage />}
        {page === 'validators' && <ValidatorsPage />}
        {page === 'inference' && <InferencePage />}
        {page === 'network' && <NetworkPage />}
        {page === 'about' && <AboutPage navigate={navigate} />}
        {page === 'research' && <ResearchPage navigate={navigate} />}
        {page === 'news' && <NewsPage navigate={navigate} />}
        {page === 'partners' && <PartnersPage navigate={navigate} />}
        {page === 'get-started' && <GetStartedPage navigate={navigate} />}
        {page === 'join' && <JoinPage navigate={navigate} />}
        {page === 'whitepaper' && <WhitepaperPage navigate={navigate} />}
      </main>
    </div>
  );
}
