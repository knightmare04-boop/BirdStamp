import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { createPortal } from 'react-dom';
import { API_BASE, resolveImageUrl } from '../api';

export default function StampCard({ 
  stamp, 
  onUpdate, 
  onDuplicate, 
  onDelete,
  options = {} 
}) {
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState(''); // 'saving', 'saved', 'error'
  const [isModalOpen, setIsModalOpen] = useState(false);
  
  // Local form state
  const [condition, setCondition] = useState(stamp.condition || '');
  const [duplicate, setDuplicate] = useState(stamp.duplicate || 'no');
  const [errorNotes, setErrorNotes] = useState(stamp.error || '');
  const [description, setDescription] = useState(stamp.description || '');
  const [elementGroup, setElementGroup] = useState(stamp.element_group || '');
  const [element, setElement] = useState(stamp.element || '');
  const [elementDescription, setElementDescription] = useState(stamp.element_description || '');

  // Keep local state in sync when stamp prop changes
  useEffect(() => {
    setCondition(stamp.condition || '');
    setDuplicate(stamp.duplicate || 'no');
    setErrorNotes(stamp.error || '');
    setDescription(stamp.description || '');
    setElementGroup(stamp.element_group || '');
    setElement(stamp.element || '');
    setElementDescription(stamp.element_description || '');
  }, [stamp]);

  const saveTimerRef = useRef(null);

  const handleUpdate = async (fieldsToUpdate) => {
    setSaving(true);
    setSaveStatus('saving');
    try {
      const response = await axios.patch(`${API_BASE}/stamps/${stamp.id}`, fieldsToUpdate);
      if (onUpdate) {
        onUpdate(response.data);
      }
      setSaveStatus('saved');
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => setSaveStatus(''), 2500);
    } catch (err) {
      console.error("Failed to update stamp", err);
      setSaveStatus('error');
    } finally {
      setSaving(false);
    }
  };

  // Condition change handler
  const handleConditionChange = (val) => {
    setCondition(val);
    handleUpdate({ condition: val });
  };

  // Element group change handler
  const handleElementGroupChange = (val) => {
    setElementGroup(val);
    handleUpdate({ element_group: val });
  };

  // Element change handler with auto-fill of Element Group and Description
  const handleElementChange = (val) => {
    setElement(val);
    const updates = { element: val };

    // Auto-fill description if available
    if (options.element_descriptions && options.element_descriptions[val]) {
      const autoDesc = options.element_descriptions[val];
      setElementDescription(autoDesc);
      updates.element_description = autoDesc;
    }

    // Auto-fill element group if not currently set or if found in options
    if (options.elements_by_group) {
      for (const [groupName, elems] of Object.entries(options.elements_by_group)) {
        if (elems.includes(val)) {
          if (!elementGroup || elementGroup !== groupName) {
            setElementGroup(groupName);
            updates.element_group = groupName;
          }
          break;
        }
      }
    }

    handleUpdate(updates);
  };

  // Filtered elements based on selected group
  const availableElements = (elementGroup && options.elements_by_group && options.elements_by_group[elementGroup])
    ? options.elements_by_group[elementGroup]
    : (options.all_elements || []);

  const conditionOptions = options.conditions || [
    "Mint Never Hinged (MNH)",
    "Mint Hinged (MH)",
    "Mint Without Gum",
    "Specimen Overprints",
    "Imperforate Varieties",
    "Color Varieties",
    "Used",
    "First Day Cover (FDC)",
    "Cancelled to Order (CTO)"
  ];

  const elementGroupOptions = options.element_groups || [
    "Design & Production",
    "Issued Stamps",
    "Postal Stationery",
    "Postal History",
    "Specialized Items",
    "Elements to Avoid"
  ];

  // Rendered inline (rather than as a nested component) so it isn't
  // recreated with a new identity on every render.
  const modalPortal = isModalOpen ? createPortal(
    <div className="stamp-modal-overlay" onClick={() => setIsModalOpen(false)}>
      <div className="stamp-modal-content" onClick={e => e.stopPropagation()}>
        <button className="stamp-modal-close" onClick={() => setIsModalOpen(false)} title="Close">&times;</button>
        <div className="stamp-modal-image">
          {stamp.image_url ? (
            <img src={resolveImageUrl(stamp.image_url)} alt={stamp.english_name} />
          ) : (
            <span style={{ color: 'var(--text-muted)' }}>No Image Available</span>
          )}
        </div>
        <div className="stamp-info" style={{ borderTop: '1px solid var(--border-subtle)', maxHeight: '42vh', overflowY: 'auto' }}>
          <div className="stamp-header">
            <div>
              <h3 className="stamp-title" style={{ fontSize: '1.35rem' }}>{stamp.english_name || 'Unknown Bird'}</h3>
              <div className="stamp-subtitle" style={{ fontSize: '0.95rem' }}>{stamp.scientific_name}</div>
            </div>
            <span className="stamp-badge" style={{ fontSize: '0.85rem' }}>{stamp.face_value || '—'}</span>
          </div>

          {/* Bird Taxonomy Breakdown */}
          <div className="modal-taxonomy-grid">
            <div className="taxonomy-item">
              <span className="taxonomy-label">Bird Group</span>
              <span className="taxonomy-value" style={{ color: 'var(--tag-group-text)' }}>{stamp.bird_group || '—'}</span>
            </div>
            <div className="taxonomy-item">
              <span className="taxonomy-label">Genus</span>
              <span className="taxonomy-value" style={{ color: 'var(--tag-genus-text)' }}><em>{stamp.genus || '—'}</em></span>
            </div>
            <div className="taxonomy-item">
              <span className="taxonomy-label">Species</span>
              <span className="taxonomy-value" style={{ color: 'var(--tag-species-text)' }}><em>{stamp.species || '—'}</em></span>
            </div>
            <div className="taxonomy-item">
              <span className="taxonomy-label">Country</span>
              <span className="taxonomy-value">{stamp.country}</span>
            </div>
            <div className="taxonomy-item">
              <span className="taxonomy-label">Year</span>
              <span className="taxonomy-value">{stamp.year}</span>
            </div>
            <div className="taxonomy-item">
              <span className="taxonomy-label">Release Date</span>
              <span className="taxonomy-value">{stamp.release_date || '—'}</span>
            </div>
          </div>

          {stamp.element && (
            <div className="modal-element-box">
              <div><strong style={{ color: 'var(--accent-gold)' }}>Element:</strong> {stamp.element} {stamp.element_group && `(${stamp.element_group})`}</div>
              {stamp.element_description && <div className="element-desc-text">{stamp.element_description}</div>}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  ) : null;

  return (
    <>
      <div className={`stamp-card ${stamp.my_collection ? 'in-collection' : ''}`}>
        <div 
          className="stamp-image-container" 
          onClick={() => setIsModalOpen(true)}
          style={{ cursor: 'zoom-in' }}
          title="Click to inspect high-resolution specimen"
        >
          {stamp.image_url ? (
            <img src={resolveImageUrl(stamp.image_url)} alt={stamp.english_name} loading="lazy" />
          ) : (
            <span style={{ color: 'var(--text-dim)', fontSize: '0.85rem' }}>No Specimen Image</span>
          )}
          {stamp.my_collection && (
            <div className="collection-badge-ribbon">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
              In Collection
            </div>
          )}
        </div>
        
        <div className="stamp-info">
          <div className="stamp-header">
            <div style={{ flex: 1, minWidth: 0 }}>
              <h3 className="stamp-title" title={stamp.english_name}>{stamp.english_name || 'Unknown Bird'}</h3>
              <div className="stamp-subtitle">{stamp.scientific_name || '—'}</div>
            </div>
            <span className="stamp-badge">{stamp.face_value || '—'}</span>
          </div>

          {/* Bird Taxonomy Display: Group (Seafoam), Genus (Moss), Species (Amber) */}
          <div className="stamp-taxonomy">
            {stamp.bird_group ? (
              <span className="taxonomy-tag group-tag" title={`Bird Group: ${stamp.bird_group}`}>
                <span className="tag-icon">🐦</span>
                <span className="tag-text">{stamp.bird_group}</span>
              </span>
            ) : null}
            {stamp.genus ? (
              <span className="taxonomy-tag genus-tag" title={`Genus: ${stamp.genus}`}>
                <span className="tag-label">G:</span>
                <span className="tag-text">{stamp.genus}</span>
              </span>
            ) : null}
            {stamp.species ? (
              <span className="taxonomy-tag species-tag" title={`Species: ${stamp.species}`}>
                <span className="tag-label">Sp:</span>
                <span className="tag-text">{stamp.species}</span>
              </span>
            ) : null}
          </div>
          
          <div className="stamp-meta">
            <span>{stamp.country}</span>
            <span>&bull;</span>
            <span>{stamp.year}</span>
          </div>
        </div>
        
        <div className="stamp-actions">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label className="checkbox-label">
              <input 
                type="checkbox" 
                checked={stamp.my_collection || false} 
                onChange={(e) => handleUpdate({ my_collection: e.target.checked })}
                disabled={saving}
              />
              <span>In My Collection</span>
            </label>
            
            {/* Real-time Save status feedback */}
            <div className="save-status-indicator">
              {saveStatus === 'saving' && <span className="status-saving">Saving...</span>}
              {saveStatus === 'saved' && <span className="status-saved">✓ Saved</span>}
              {saveStatus === 'error' && <span className="status-error">✕ Error</span>}
            </div>
          </div>
          
          {/* Condition: Autofill with Dropdown */}
          <div className="editable-field">
            <label>Condition</label>
            <div className="autofill-wrapper">
              <input 
                type="text" 
                list={`conditions-${stamp.id}`}
                className="editable-input" 
                placeholder="Select or type condition..."
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                onBlur={(e) => {
                  if (e.target.value !== (stamp.condition || '')) {
                    handleConditionChange(e.target.value);
                  }
                }}
              />
              <datalist id={`conditions-${stamp.id}`}>
                {conditionOptions.map((opt) => (
                  <option key={opt} value={opt} />
                ))}
              </datalist>
            </div>
          </div>
          
          <div className="editable-field">
            <label>Duplicate</label>
            <select
              className="editable-input editable-select"
              style={{ width: '85px' }}
              value={duplicate}
              onChange={(e) => {
                const val = e.target.value;
                setDuplicate(val);
                handleUpdate({ duplicate: val });
              }}
            >
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </select>
          </div>
          
          <div className="editable-field">
            <label>Error Notes</label>
            <input 
              type="text" 
              className="editable-input" 
              placeholder="e.g. Inverted center, missing color"
              value={errorNotes}
              onChange={(e) => setErrorNotes(e.target.value)}
              onBlur={(e) => {
                if (e.target.value !== (stamp.error || '')) {
                  handleUpdate({ error: e.target.value });
                }
              }}
            />
          </div>
          
          <div className="editable-field field-vertical">
            <label>Description / Notes</label>
            <textarea 
              className="editable-input" 
              placeholder="Add personal notes..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={(e) => {
                if (e.target.value !== (stamp.description || '')) {
                  handleUpdate({ description: e.target.value });
                }
              }}
              style={{ resize: 'vertical', minHeight: '48px' }}
            />
          </div>
          
          {stamp.my_collection && (
            <div className="collection-fields-section">
              {/* Element Group: Autofill with Dropdown */}
              <div className="editable-field">
                <label>Element Group</label>
                <div className="autofill-wrapper">
                  <input 
                    type="text" 
                    list={`element-groups-${stamp.id}`}
                    className="editable-input" 
                    placeholder="Select or type element group..."
                    value={elementGroup}
                    onChange={(e) => setElementGroup(e.target.value)}
                    onBlur={(e) => {
                      if (e.target.value !== (stamp.element_group || '')) {
                        handleElementGroupChange(e.target.value);
                      }
                    }}
                  />
                  <datalist id={`element-groups-${stamp.id}`}>
                    {elementGroupOptions.map((eg) => (
                      <option key={eg} value={eg} />
                    ))}
                  </datalist>
                </div>
              </div>

              {/* Element: Autofill with Dropdown + Auto-fills Group & Description */}
              <div className="editable-field">
                <label>Element</label>
                <div className="autofill-wrapper">
                  <input 
                    type="text" 
                    list={`elements-${stamp.id}`}
                    className="editable-input" 
                    placeholder="Select or type element..."
                    value={element}
                    onChange={(e) => {
                      const val = e.target.value;
                      setElement(val);
                      if (options.all_elements && options.all_elements.includes(val)) {
                        handleElementChange(val);
                      }
                    }}
                    onBlur={(e) => {
                      if (e.target.value !== (stamp.element || '')) {
                        handleElementChange(e.target.value);
                      }
                    }}
                  />
                  <datalist id={`elements-${stamp.id}`}>
                    {availableElements.map((elem) => (
                      <option key={elem} value={elem} />
                    ))}
                  </datalist>
                </div>
              </div>

              {/* Element Description */}
              <div className="editable-field field-vertical">
                <label>Element Description</label>
                <textarea 
                  className="editable-input" 
                  placeholder="Element description (auto-filled or custom)..."
                  value={elementDescription}
                  onChange={(e) => setElementDescription(e.target.value)}
                  onBlur={(e) => {
                    if (e.target.value !== (stamp.element_description || '')) {
                      handleUpdate({ element_description: e.target.value });
                    }
                  }}
                  style={{ resize: 'vertical', minHeight: '50px', fontSize: '0.8rem' }}
                />
              </div>
            </div>
          )}

          <div className="card-button-row">
            <button 
              className="btn btn-secondary btn-sm" 
              onClick={() => onDuplicate && onDuplicate(stamp)}
              disabled={saving}
              title="Create another copy of this stamp entry"
            >
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              Duplicate
            </button>
            <button 
              className="btn btn-secondary btn-sm btn-delete" 
              onClick={() => onDelete && onDelete(stamp)}
              disabled={saving}
              title="Delete this entry"
            >
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
              Delete
            </button>
          </div>
        </div>
      </div>
      {modalPortal}
    </>
  );
}
