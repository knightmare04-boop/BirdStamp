import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import StampCard from './components/StampCard';
import CreateCardModal from './components/CreateCardModal';
import ToastContainer from './components/Toast';
import ConfirmDialog from './components/ConfirmDialog';
import { API_BASE } from './api';

// localStorage can throw (private browsing, disabled storage, quota, etc.),
// so every access goes through these small wrappers.
function safeGetItem(key, fallback = null) {
  try {
    const val = localStorage.getItem(key);
    return val === null ? fallback : val;
  } catch {
    return fallback;
  }
}

function safeSetItem(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore — nothing we can do if storage is unavailable
  }
}

function App() {
  const [stamps, setStamps] = useState([]);
  const [totalStamps, setTotalStamps] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const scrollContainerRef = useRef(null);

  // Theme state: 'dark' or 'light'
  const [theme, setTheme] = useState(() => safeGetItem('birdstamp_theme', 'dark'));

  // Apply theme to html root
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    safeSetItem('birdstamp_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => (prev === 'dark' ? 'light' : 'dark'));
  };

  const [searchTerm, setSearchTerm] = useState(() => safeGetItem('searchTerm', ''));
  const [debouncedSearch, setDebouncedSearch] = useState(() => safeGetItem('searchTerm', ''));
  const [filterCountry, setFilterCountry] = useState(() => safeGetItem('filterCountry', ''));
  const [debouncedCountry, setDebouncedCountry] = useState(() => safeGetItem('filterCountry', ''));
  const [availableCountries, setAvailableCountries] = useState([]);
  const [filterElementGroup, setFilterElementGroup] = useState(() => safeGetItem('filterElementGroup', ''));
  const [debouncedElementGroup, setDebouncedElementGroup] = useState(() => safeGetItem('filterElementGroup', ''));
  const [filterElement, setFilterElement] = useState(() => safeGetItem('filterElement', ''));
  const [debouncedElement, setDebouncedElement] = useState(() => safeGetItem('filterElement', ''));
  const [filterCollection, setFilterCollection] = useState(() => safeGetItem('filterCollection', 'all'));

  // Philatelic options for dropdowns & auto-completion
  const [options, setOptions] = useState({
    conditions: [],
    element_groups: [],
    elements_by_group: {},
    all_elements: [],
    element_descriptions: {}
  });

  const [page, setPage] = useState(() => parseInt(safeGetItem('page'), 10) || 1);
  const limit = 100;

  const [status, setStatus] = useState({ scrape: {}, sync: {} });
  const [isExporting, setIsExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, variant = 'success') => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts(prev => [...prev, { id, message, variant }]);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // Persist filter/search state to localStorage
  useEffect(() => {
    safeSetItem('searchTerm', searchTerm);
    safeSetItem('filterCountry', filterCountry);
    safeSetItem('filterElementGroup', filterElementGroup);
    safeSetItem('filterElement', filterElement);
    safeSetItem('filterCollection', filterCollection);
    safeSetItem('page', page);
  }, [searchTerm, filterCountry, filterElementGroup, filterElement, filterCollection, page]);

  // Debounce search and filter inputs. The page is reset to 1 whenever
  // these inputs actually change, but NOT on the initial mount run — that
  // would otherwise discard the page number restored from localStorage.
  const isFirstDebounceRun = useRef(true);
  useEffect(() => {
    const shouldResetPage = !isFirstDebounceRun.current;
    isFirstDebounceRun.current = false;

    const handler = setTimeout(() => {
      setDebouncedSearch(searchTerm);
      setDebouncedCountry(filterCountry);
      setDebouncedElementGroup(filterElementGroup);
      setDebouncedElement(filterElement);
      if (shouldResetPage) {
        setPage(1);
      }
    }, 350);
    return () => clearTimeout(handler);
  }, [searchTerm, filterCountry, filterElementGroup, filterElement]);

  // Reset to page 1 when collection filter changes
  const handleCollectionChange = (e) => {
    setFilterCollection(e.target.value);
    setPage(1);
  };

  const fetchStamps = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page,
        limit,
        collection_status: filterCollection
      });
      if (debouncedSearch) params.append('search', debouncedSearch);
      if (debouncedCountry) params.append('country', debouncedCountry);
      if (debouncedElementGroup) params.append('element_group', debouncedElementGroup);
      if (debouncedElement) params.append('element', debouncedElement);

      const response = await axios.get(`${API_BASE}/stamps?${params.toString()}`);
      setStamps(response.data.items);
      setTotalStamps(response.data.total);
      setFetchError(false);
    } catch (err) {
      console.error("Failed to fetch stamps", err);
      setFetchError(true);
    } finally {
      setLoading(false);
    }
  }, [page, limit, filterCollection, debouncedSearch, debouncedCountry, debouncedElementGroup, debouncedElement]);

  useEffect(() => {
    fetchStamps();
  }, [fetchStamps]);

  // Fetch available countries for dropdown
  const fetchCountries = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE}/countries`);
      setAvailableCountries(response.data);
    } catch (err) {
      console.error("Failed to fetch countries", err);
      setFetchError(true);
    }
  }, []);

  useEffect(() => {
    fetchCountries();
  }, [fetchCountries]);

  // Fetch philatelic dropdown options from backend
  const fetchOptions = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE}/options`);
      setOptions(response.data);
    } catch (err) {
      console.error("Failed to fetch philatelic options", err);
      setFetchError(true);
    }
  }, []);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  const handleRetry = () => {
    setFetchError(false);
    fetchStamps();
    fetchCountries();
    fetchOptions();
  };

  // Restore scroll position after stamps load
  useEffect(() => {
    if (!loading && stamps.length > 0 && scrollContainerRef.current) {
      const savedScroll = safeGetItem('scrollPosition');
      if (savedScroll) {
        scrollContainerRef.current.scrollTop = parseInt(savedScroll, 10);
      }
    }
  }, [loading, stamps]);

  const handleScroll = () => {
    if (scrollContainerRef.current) {
      safeSetItem('scrollPosition', scrollContainerRef.current.scrollTop);
    }
  };

  // Status polling: one fetch on mount, then keep polling only while a
  // scrape or sync job is actually running, or for ~10s after the user
  // starts one (so we quickly notice it starting).
  const [pollBurst, setPollBurst] = useState(false);
  const pollBurstTimerRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/status`);
      setStatus(res.data);
    } catch {
      // ignore transient status polling errors
    }
  }, []);

  const startPollingBurst = useCallback(() => {
    setPollBurst(true);
    if (pollBurstTimerRef.current) clearTimeout(pollBurstTimerRef.current);
    pollBurstTimerRef.current = setTimeout(() => setPollBurst(false), 10000);
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const isScrapeRunning = Boolean(status.scrape?.is_running);
  const isSyncRunning = Boolean(status.sync?.is_running);

  useEffect(() => {
    if (!isScrapeRunning && !isSyncRunning && !pollBurst) return undefined;
    const interval = setInterval(fetchStatus, 1500);
    return () => clearInterval(interval);
  }, [isScrapeRunning, isSyncRunning, pollBurst, fetchStatus]);

  // Clean up the polling-burst timer on unmount
  useEffect(() => {
    return () => {
      if (pollBurstTimerRef.current) clearTimeout(pollBurstTimerRef.current);
    };
  }, []);

  // Refetch stamps once a sync job transitions from running -> finished
  const prevSyncRunningRef = useRef(false);
  useEffect(() => {
    if (prevSyncRunningRef.current && !isSyncRunning) {
      fetchStamps();
    }
    prevSyncRunningRef.current = isSyncRunning;
  }, [isSyncRunning, fetchStamps]);

  const handleScrape = async () => {
    try {
      await axios.post(`${API_BASE}/scrape`);
      showToast("Full scrape initiated in background.", 'success');
      startPollingBurst();
    } catch (error) {
      console.error(error);
      showToast(error.response?.data?.detail || "Failed to trigger scrape.", 'error');
    }
  };

  const handleSync = async () => {
    let excelPath = null;

    // window.pywebview is injected asynchronously by the desktop shell
    // (after the 'pywebviewready' event), so this must be checked here at
    // click time rather than cached at mount.
    if (window.pywebview?.api?.pick_excel) {
      try {
        const result = await window.pywebview.api.pick_excel();
        excelPath = Array.isArray(result) ? result[0] : result;
      } catch (err) {
        console.error("Failed to open Excel file picker", err);
        showToast("Failed to open the file picker.", 'error');
        return;
      }
      if (!excelPath) return;
    }

    try {
      await axios.post(`${API_BASE}/sync`, excelPath ? { excel_path: excelPath } : {});
      showToast("Sync started", 'success');
      startPollingBurst();
    } catch (error) {
      console.error(error);
      showToast(error.response?.data?.detail || "Failed to start sync.", 'error');
    }
  };

  const handleExport = async () => {
    if (isExporting) return;
    setIsExporting(true);
    setExportMessage("Exporting Excel sheet...");
    try {
      const res = await axios.post(`${API_BASE}/export`);
      const data = res.data || {};
      let message = data.message || "Export successful!";
      if (data.folder && !message.includes(data.folder)) {
        message = `${message} (${data.folder})`;
      }
      setExportMessage(message);
    } catch (error) {
      console.error(error);
      setExportMessage("Export failed.");
    } finally {
      setIsExporting(false);
      setTimeout(() => setExportMessage(''), 4500);
    }
  };

  const handleUpdateStamp = (updatedStamp) => {
    setStamps(stamps.map(s => s.id === updatedStamp.id ? updatedStamp : s));
  };

  const handleStampCreated = (newStamp) => {
    setStamps(prev => [newStamp, ...prev]);
    setTotalStamps(prev => prev + 1);
    setExportMessage(`Specimen "${newStamp.english_name || 'Stamp'}" cataloged successfully!`);
    setTimeout(() => setExportMessage(''), 5000);
  };

  const handleDuplicateStamp = async (stamp) => {
    try {
      await axios.post(`${API_BASE}/stamps/${stamp.id}/duplicate`);
      fetchStamps();
    } catch (err) {
      console.error("Failed to duplicate stamp", err);
      showToast("Failed to duplicate stamp.", 'error');
    }
  };

  const handleDeleteStamp = (stamp) => {
    setConfirmDelete(stamp);
  };

  const confirmDeleteStamp = async () => {
    const stamp = confirmDelete;
    setConfirmDelete(null);
    if (!stamp) return;
    try {
      await axios.delete(`${API_BASE}/stamps/${stamp.id}`);
      fetchStamps();
    } catch (err) {
      console.error("Failed to delete stamp", err);
      showToast("Failed to delete stamp.", 'error');
    }
  };

  const totalPages = Math.ceil(totalStamps / limit);

  // Available elements in sidebar based on element group filter
  const filterElementsList = (filterElementGroup && options.elements_by_group && options.elements_by_group[filterElementGroup])
    ? options.elements_by_group[filterElementGroup]
    : (options.all_elements || []);

  const hasActiveFilters = Boolean(
    searchTerm || filterCountry || filterElementGroup || filterElement || filterCollection !== 'all'
  );

  return (
    <div className="app-container">
      <header className="header">
        <div className="header-brand">
          <div className="brand-icon-box">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          </div>
          <div className="brand-titles">
            <h1>BirdStamp Tracker</h1>
            <span className="brand-subtitle">Naturalist & Philatelic Archive</span>
          </div>
        </div>

        <div style={{ flex: 1, margin: '0 1.5rem', maxWidth: '460px' }}>
          {(status.scrape?.is_running || status.sync?.is_running) && (
            <div className="status-panel">
              {status.scrape?.is_running && (
                <div className="status-item">
                  <div className="status-header">
                    <span>Scraping Data: {status.scrape.message}</span>
                    <span>{status.scrape.progress} / {status.scrape.total}</span>
                  </div>
                  <div className="progress-container">
                    <div className="progress-bar" style={{ width: `${status.scrape.total ? (status.scrape.progress / status.scrape.total) * 100 : 0}%` }}></div>
                  </div>
                </div>
              )}
              {status.sync?.is_running && (
                <div className="status-item">
                  <div className="status-header">
                    <span>Syncing Excel: {status.sync.message}</span>
                    <span>{status.sync.progress} / {status.sync.total}</span>
                  </div>
                  <div className="progress-container">
                    <div className="progress-bar" style={{ width: `${status.sync.total ? (status.sync.progress / status.sync.total) * 100 : 0}%` }}></div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="header-right">
          {/* Smooth Morphing Theme Toggle Button */}
          <button
            className={`theme-toggle-btn ${theme === 'dark' ? 'is-dark' : 'is-light'}`}
            onClick={toggleTheme}
            title={`Switch to ${theme === 'dark' ? 'Light (Parchment)' : 'Dark (Espresso)'} Mode`}
            aria-label="Toggle Color Theme"
          >
            {/* Sun Icon */}
            <svg className="theme-icon theme-icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"/>
              <line x1="12" y1="1" x2="12" y2="3"/>
              <line x1="12" y1="21" x2="12" y2="23"/>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
              <line x1="1" y1="12" x2="3" y2="12"/>
              <line x1="21" y1="12" x2="23" y2="12"/>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
            </svg>

            {/* Moon Icon */}
            <svg className="theme-icon theme-icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          </button>

          <div className="actions">
            {exportMessage && (
              <span style={{ marginRight: '0.5rem', color: exportMessage.includes('fail') ? 'var(--coral-500)' : 'var(--moss-600)', fontWeight: '700', fontSize: '0.82rem' }}>
                {exportMessage}
              </span>
            )}
            <button
              className="btn btn-create-card"
              onClick={() => setIsCreateModalOpen(true)}
              title="Catalog your own custom stamp card with picture and full taxonomy"
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              Create Card
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleSync}
              disabled={isScrapeRunning || isSyncRunning}
              title="Sync collection status from an Excel workbook"
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Sync from Excel
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleExport}
              disabled={isExporting}
              title="Export database and collection records to Excel sheet in 'my collection sheets'"
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {isExporting ? "Exporting..." : "Export Excel Sheet"}
            </button>
            <button
              className="btn"
              onClick={handleScrape}
              disabled={isScrapeRunning || isSyncRunning}
              title="Trigger full bird theme web scraper"
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
              Trigger Scrape
            </button>
          </div>
        </div>
      </header>

      <main className="main-content">
        <aside className="sidebar">
          <div>
            <div className="sidebar-section-title">Search & Taxonomy</div>
            <div className="filter-group">
              <label>Bird / Taxonomy Search</label>
              <div className="filter-input-wrapper">
                <span className="filter-input-icon">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                </span>
                <input
                  type="text"
                  placeholder="e.g. Falcon, Falco, biarmicus..."
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                />
              </div>
            </div>
          </div>

          <div>
            <div className="sidebar-section-title">Geography</div>
            <div className="filter-group">
              <label>Filter by Country</label>
              <select
                value={filterCountry}
                onChange={e => setFilterCountry(e.target.value)}
              >
                <option value="">All Countries ({availableCountries.length})</option>
                {availableCountries.map(country => (
                  <option key={country} value={country}>{country}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <div className="sidebar-section-title">Philatelic Classification</div>
            <div className="filter-group" style={{ marginBottom: '0.75rem' }}>
              <label>Element Group</label>
              <select
                value={filterElementGroup}
                onChange={e => {
                  setFilterElementGroup(e.target.value);
                  setFilterElement('');
                }}
              >
                <option value="">All Element Groups</option>
                {(options.element_groups || []).map(group => (
                  <option key={group} value={group}>{group}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label>Element</label>
              <select
                value={filterElement}
                onChange={e => setFilterElement(e.target.value)}
              >
                <option value="">All Elements ({filterElementsList.length})</option>
                {filterElementsList.map(elem => (
                  <option key={elem} value={elem}>{elem}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <div className="sidebar-section-title">Collection State</div>
            <div className="filter-group">
              <label>Status</label>
              <select value={filterCollection} onChange={handleCollectionChange}>
                <option value="all">All Stamps</option>
                <option value="owned">In My Collection</option>
                <option value="missing">Missing</option>
              </select>
            </div>
          </div>

          {hasActiveFilters && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setSearchTerm('');
                setFilterCountry('');
                setFilterElementGroup('');
                setFilterElement('');
                setFilterCollection('all');
                setPage(1);
              }}
              style={{ marginTop: '0.25rem', justifyContent: 'center' }}
            >
              Reset Filters
            </button>
          )}

          <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Showing <strong style={{ color: 'var(--accent-gold)' }}>{totalStamps.toLocaleString()}</strong> stamps
            </p>
          </div>
        </aside>

        <section className="main-feed" style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          <div
            className="grid-container"
            style={{ flex: 1, overflowY: 'auto' }}
            ref={scrollContainerRef}
            onScroll={handleScroll}
          >
            {loading ? (
              <div className="status-indicator" style={{ gridColumn: '1 / -1' }}>Loading specimens...</div>
            ) : fetchError ? (
              <div className="empty-state error-state">
                <h3>Couldn't load stamps</h3>
                <p>Something went wrong while contacting the server. Please try again.</p>
                <button className="btn btn-secondary" onClick={handleRetry}>Retry</button>
              </div>
            ) : stamps.length > 0 ? (
              stamps.map(stamp => (
                <StampCard
                  key={stamp.id}
                  stamp={stamp}
                  options={options}
                  onUpdate={handleUpdateStamp}
                  onDuplicate={handleDuplicateStamp}
                  onDelete={handleDeleteStamp}
                />
              ))
            ) : (
              <div className="empty-state">
                <h3>No specimen stamps found</h3>
                <p>Try adjusting your search criteria or philatelic filters.</p>
              </div>
            )}
          </div>

          {!loading && !fetchError && totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn btn-secondary btn-sm"
                disabled={page === 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Page <strong style={{ color: 'var(--text-primary)' }}>{page}</strong> of <strong style={{ color: 'var(--text-primary)' }}>{totalPages}</strong>
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              >
                Next
              </button>
            </div>
          )}
        </section>
      </main>

      {/* key={isCreateModalOpen} forces a fresh instance each time the
          modal is opened, so its form state always starts clean. */}
      <CreateCardModal
        key={isCreateModalOpen}
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSuccess={handleStampCreated}
        availableCountries={availableCountries}
        options={options}
      />

      <ConfirmDialog
        isOpen={Boolean(confirmDelete)}
        title="Delete Stamp Entry"
        message={`Are you sure you want to delete "${confirmDelete?.english_name || confirmDelete?.scientific_name || 'this entry'}"? This cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={confirmDeleteStamp}
        onCancel={() => setConfirmDelete(null)}
      />

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default App;
