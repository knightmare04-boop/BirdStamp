import { useState } from 'react';
import axios from 'axios';
import { API_BASE } from '../api';

export default function UpdateBanner({ update, onError }) {
  const [dismissedVersion, setDismissedVersion] = useState(null);
  const [isRestarting, setIsRestarting] = useState(false);

  if (!update || update.status !== 'ready' || !update.latest_version) return null;
  if (dismissedVersion === update.latest_version && !isRestarting) return null;

  const handleRestart = async () => {
    setIsRestarting(true);
    try {
      await axios.post(`${API_BASE}/update/apply`);
      // The window closes and the updated app reopens by itself.
    } catch (error) {
      setIsRestarting(false);
      onError?.(error.response?.data?.detail || 'Could not start the update.');
    }
  };

  return (
    <div className="update-banner" role="status">
      <svg className="update-banner-icon" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
      <div className="update-banner-text">
        {isRestarting ? (
          <strong>Installing version {update.latest_version}... BirdStamp will reopen in a moment.</strong>
        ) : (
          <>
            <strong>Version {update.latest_version} is ready to install.</strong>
            <span>Restart now, or it will install automatically next time you open BirdStamp. Your collection is not affected.</span>
          </>
        )}
      </div>
      {!isRestarting && (
        <div className="update-banner-actions">
          <button type="button" className="btn btn-sm" onClick={handleRestart}>
            Restart to update
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setDismissedVersion(update.latest_version)}
          >
            Later
          </button>
        </div>
      )}
    </div>
  );
}
