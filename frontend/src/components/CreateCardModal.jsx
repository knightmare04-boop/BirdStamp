import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { API_BASE } from '../api';

export default function CreateCardModal({
  isOpen,
  onClose,
  onSuccess,
  availableCountries = [],
  options = {}
}) {
  // Form State
  const [englishName, setEnglishName] = useState('');
  const [scientificName, setScientificName] = useState('');
  const [country, setCountry] = useState('');
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [faceValue, setFaceValue] = useState('');
  const [releaseDate, setReleaseDate] = useState('');
  
  // Taxonomy
  const [birdGroup, setBirdGroup] = useState('');
  const [genus, setGenus] = useState('');
  const [species, setSpecies] = useState('');
  const [category, setCategory] = useState('Commemorative');
  const [stampType, setStampType] = useState('Postage');

  // Philatelic Classification
  const [elementGroup, setElementGroup] = useState('');
  const [element, setElement] = useState('');
  const [elementDescription, setElementDescription] = useState('');

  // Collection details
  const [myCollection, setMyCollection] = useState(true);
  const [condition, setCondition] = useState('Mint Never Hinged (MNH)');
  const [duplicate, setDuplicate] = useState('no');
  const [errorNotes, setErrorNotes] = useState('');
  const [description, setDescription] = useState('');

  // Image Upload State
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState('');
  const [imageUrlInput, setImageUrlInput] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef(null);

  // Status & Validation
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStep, setSubmitStep] = useState(''); // 'uploading', 'saving'
  const [errorMessage, setErrorMessage] = useState('');

  // Revoke the previous object-URL preview whenever it is replaced or
  // cleared, and on unmount, so we don't leak blob URLs.
  useEffect(() => {
    return () => {
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview);
      }
    };
  }, [imagePreview]);

  // Auto-fill genus and species when scientific name changes
  const handleScientificNameChange = (val) => {
    setScientificName(val);
    const parts = val.trim().split(/\s+/);
    if (parts.length >= 1 && parts[0] && !genus) {
      setGenus(parts[0]);
    }
    if (parts.length >= 2 && parts[1] && !species) {
      setSpecies(parts[1]);
    }
  };

  // Auto-fill group & description when element changes
  const handleElementChange = (val) => {
    setElement(val);
    if (!val) return;

    if (options.element_descriptions && options.element_descriptions[val]) {
      setElementDescription(options.element_descriptions[val]);
    }

    if (options.elements_by_group) {
      for (const [groupName, elems] of Object.entries(options.elements_by_group)) {
        if (elems.includes(val)) {
          if (!elementGroup || elementGroup !== groupName) {
            setElementGroup(groupName);
          }
          break;
        }
      }
    }
  };

  // Image handling
  const handleFileSelect = (file) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setErrorMessage('Please select a valid image file (JPEG, PNG, WEBP, GIF).');
      return;
    }
    setImageFile(file);
    setImageUrlInput('');
    setErrorMessage('');
    const previewUrl = URL.createObjectURL(file);
    setImagePreview(previewUrl);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const clearImage = () => {
    setImageFile(null);
    setImagePreview('');
    setImageUrlInput('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');

    if (!englishName.trim() && !scientificName.trim()) {
      setErrorMessage('Please provide at least an English Name or Scientific Name for the specimen.');
      return;
    }

    setIsSubmitting(true);
    let finalImageUrl = imageUrlInput.trim();

    try {
      // 1. Upload picture if local file selected
      if (imageFile) {
        setSubmitStep('Uploading specimen image...');
        const formData = new FormData();
        formData.append('file', imageFile);

        const uploadRes = await axios.post(`${API_BASE}/upload-image`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        finalImageUrl = uploadRes.data?.image_url || '';
      }

      // 2. Save stamp entry in backend
      setSubmitStep('Cataloging stamp into database...');
      const payload = {
        english_name: englishName.trim(),
        scientific_name: scientificName.trim(),
        country: country.trim(),
        year: year.trim(),
        face_value: faceValue.trim(),
        release_date: releaseDate.trim(),
        bird_group: birdGroup.trim(),
        genus: genus.trim(),
        species: species.trim(),
        category: category.trim(),
        stamp_type: stampType.trim(),
        image_url: finalImageUrl,
        my_collection: myCollection,
        condition: condition.trim(),
        duplicate: duplicate.trim(),
        error: errorNotes.trim(),
        description: description.trim(),
        element_group: elementGroup.trim(),
        element: element.trim(),
        element_description: elementDescription.trim()
      };

      const createRes = await axios.post(`${API_BASE}/stamps`, payload);
      
      if (onSuccess) {
        onSuccess(createRes.data);
      }
      onClose();
    } catch (err) {
      console.error('Failed to create stamp card:', err);
      const detail = err.response?.data?.detail || err.message || 'Error creating stamp';
      setErrorMessage(`Failed to create card: ${detail}`);
    } finally {
      setIsSubmitting(false);
      setSubmitStep('');
    }
  };

  // Available elements for dropdown based on chosen element group
  const availableElements = (elementGroup && options.elements_by_group && options.elements_by_group[elementGroup])
    ? options.elements_by_group[elementGroup]
    : (options.all_elements || []);

  if (!isOpen) return null;

  return (
    <div className="stamp-modal-overlay" onClick={onClose}>
      <div 
        className="stamp-modal-content create-card-modal-content" 
        onClick={e => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="create-modal-header">
          <div className="create-modal-header-title">
            <div className="brand-icon-box create-icon-badge">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <div>
              <h2>Create Stamp Card</h2>
              <span className="create-modal-subtitle">Catalog a custom specimen with full taxonomy & philatelic data</span>
            </div>
          </div>
          <button className="stamp-modal-close" onClick={onClose} title="Close dialog">&times;</button>
        </div>

        {/* Modal Body / Form */}
        <form onSubmit={handleSubmit} className="create-card-form">
          {errorMessage && (
            <div className="create-card-alert error">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span>{errorMessage}</span>
            </div>
          )}

          <div className="create-card-layout-grid">
            {/* LEFT COLUMN: Image Upload Stage */}
            <div className="create-card-media-col">
              <label className="create-section-label">
                <span>Specimen Photograph</span>
                <span className="required-tag">Recommended</span>
              </label>

              <div 
                className={`image-dropzone ${isDragOver ? 'dragover' : ''} ${imagePreview || imageUrlInput ? 'has-preview' : ''}`}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => !imagePreview && fileInputRef.current?.click()}
              >
                <input 
                  type="file" 
                  ref={fileInputRef}
                  accept="image/png, image/jpeg, image/jpg, image/webp, image/gif"
                  style={{ display: 'none' }}
                  onChange={e => handleFileSelect(e.target.files[0])}
                />

                {imagePreview || imageUrlInput ? (
                  <div className="dropzone-preview-box">
                    <img src={imagePreview || imageUrlInput} alt="Specimen Preview" className="dropzone-preview-img" />
                    <div className="preview-overlay-actions">
                      <button 
                        type="button" 
                        className="btn-preview-action" 
                        onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                        title="Replace photo"
                      >
                        Change Photo
                      </button>
                      <button 
                        type="button" 
                        className="btn-preview-action danger" 
                        onClick={(e) => { e.stopPropagation(); clearImage(); }}
                        title="Remove photo"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="dropzone-empty-state">
                    <div className="dropzone-icon">
                      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                        <circle cx="8.5" cy="8.5" r="1.5"/>
                        <polyline points="21 15 16 10 5 21"/>
                      </svg>
                    </div>
                    <p className="dropzone-title">Click or Drag & Drop Photo Here</p>
                    <span className="dropzone-hint">PNG, JPG, WEBP, or GIF up to 25MB</span>
                  </div>
                )}
              </div>

              {/* Alternative: Image URL */}
              <div className="create-field-group url-fallback-group">
                <label>Or Paste Direct Image Web URL</label>
                <div className="filter-input-wrapper">
                  <span className="filter-input-icon">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                  </span>
                  <input 
                    type="text" 
                    placeholder="https://example.com/stamp.jpg" 
                    value={imageUrlInput}
                    onChange={(e) => {
                      setImageUrlInput(e.target.value);
                      if (e.target.value) setImageFile(null);
                    }}
                  />
                </div>
              </div>

              {/* In My Collection Toggle */}
              <div className="collection-toggle-card">
                <div className="collection-toggle-info">
                  <span className="collection-toggle-title">Add to My Collection</span>
                  <span className="collection-toggle-desc">Marks stamp as owned in archive & active spreadsheets</span>
                </div>
                <label className="switch">
                  <input 
                    type="checkbox" 
                    checked={myCollection}
                    onChange={e => setMyCollection(e.target.checked)}
                  />
                  <span className="slider round"></span>
                </label>
              </div>
            </div>

            {/* RIGHT COLUMN: Field Tabs & Inputs */}
            <div className="create-card-fields-col">
              {/* Section 1: Core Identification */}
              <div className="create-form-section">
                <div className="create-section-header">
                  <span className="section-step">1</span>
                  <h3>Stamp Identity & Origin</h3>
                </div>
                
                <div className="create-grid-2">
                  <div className="create-field-group">
                    <label>English Common Name *</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Bald Eagle, Barn Owl..." 
                      value={englishName}
                      onChange={e => setEnglishName(e.target.value)}
                      required
                    />
                  </div>

                  <div className="create-field-group">
                    <label>Scientific Binomial Name</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Haliaeetus leucocephalus" 
                      value={scientificName}
                      onChange={e => handleScientificNameChange(e.target.value)}
                    />
                  </div>
                </div>

                <div className="create-grid-3">
                  <div className="create-field-group">
                    <label>Country / Territory</label>
                    <input 
                      type="text" 
                      list="create-country-list"
                      placeholder="e.g. Canada, Iceland..." 
                      value={country}
                      onChange={e => setCountry(e.target.value)}
                    />
                    <datalist id="create-country-list">
                      {availableCountries.map(c => <option key={c} value={c} />)}
                    </datalist>
                  </div>

                  <div className="create-field-group">
                    <label>Issue Year</label>
                    <input 
                      type="text" 
                      placeholder="e.g. 2024" 
                      value={year}
                      onChange={e => setYear(e.target.value)}
                    />
                  </div>

                  <div className="create-field-group">
                    <label>Face Value / Denom.</label>
                    <input 
                      type="text" 
                      placeholder="e.g. £1.25, 40c, 5kr" 
                      value={faceValue}
                      onChange={e => setFaceValue(e.target.value)}
                    />
                  </div>
                </div>

                <div className="create-grid-2">
                  <div className="create-field-group">
                    <label>Release Date</label>
                    <input 
                      type="text" 
                      placeholder="e.g. 2024-05-18" 
                      value={releaseDate}
                      onChange={e => setReleaseDate(e.target.value)}
                    />
                  </div>
                  <div className="create-field-group">
                    <label>Issue Category</label>
                    <select value={category} onChange={e => setCategory(e.target.value)}>
                      <option value="Commemorative">Commemorative</option>
                      <option value="Definitive">Definitive</option>
                      <option value="Special Issue">Special Issue</option>
                      <option value="Semi-Postal">Semi-Postal</option>
                      <option value="Airmail">Airmail</option>
                      <option value="Official">Official</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Section 2: Bird Taxonomy */}
              <div className="create-form-section">
                <div className="create-section-header">
                  <span className="section-step">2</span>
                  <h3>Ornithological Taxonomy</h3>
                </div>

                <div className="create-grid-3">
                  <div className="create-field-group">
                    <label>Bird Group</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Hawks, Eagles" 
                      value={birdGroup}
                      onChange={e => setBirdGroup(e.target.value)}
                    />
                  </div>

                  <div className="create-field-group">
                    <label>Genus</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Haliaeetus" 
                      value={genus}
                      onChange={e => setGenus(e.target.value)}
                    />
                  </div>

                  <div className="create-field-group">
                    <label>Species</label>
                    <input 
                      type="text" 
                      placeholder="e.g. leucocephalus" 
                      value={species}
                      onChange={e => setSpecies(e.target.value)}
                    />
                  </div>
                </div>

                <div className="create-grid-2">
                  <div className="create-field-group">
                    <label>Stamp Format / Type</label>
                    <select value={stampType} onChange={e => setStampType(e.target.value)}>
                      <option value="Postage">Postage</option>
                      <option value="Souvenir Sheet">Souvenir Sheet</option>
                      <option value="Miniature Sheet">Miniature Sheet</option>
                      <option value="Booklet Pane">Booklet Pane</option>
                      <option value="Coil Stamp">Coil Stamp</option>
                      <option value="First Day Cover">First Day Cover</option>
                      <option value="Maximum Card">Maximum Card</option>
                    </select>
                  </div>

                  <div className="create-field-group">
                    <label>Condition / State</label>
                    <select value={condition} onChange={e => setCondition(e.target.value)}>
                      {(options.conditions && options.conditions.length > 0) ? (
                        options.conditions.map(cond => (
                          <option key={cond} value={cond}>{cond}</option>
                        ))
                      ) : (
                        <>
                          <option value="Mint Never Hinged (MNH)">Mint Never Hinged (MNH)</option>
                          <option value="Mint Hinged (MH)">Mint Hinged (MH)</option>
                          <option value="Used">Used</option>
                          <option value="First Day Cover (FDC)">First Day Cover (FDC)</option>
                          <option value="Cancelled to Order (CTO)">Cancelled to Order (CTO)</option>
                        </>
                      )}
                    </select>
                  </div>
                </div>
              </div>

              {/* Section 3: Philatelic Elements */}
              <div className="create-form-section">
                <div className="create-section-header">
                  <span className="section-step">3</span>
                  <h3>Philatelic Classification</h3>
                </div>

                <div className="create-grid-2">
                  <div className="create-field-group">
                    <label>Element Group</label>
                    <select 
                      value={elementGroup} 
                      onChange={e => {
                        setElementGroup(e.target.value);
                        setElement('');
                      }}
                    >
                      <option value="">-- Select Element Group --</option>
                      {options.element_groups && options.element_groups.map(grp => (
                        <option key={grp} value={grp}>{grp}</option>
                      ))}
                    </select>
                  </div>

                  <div className="create-field-group">
                    <label>Specific Element</label>
                    <select 
                      value={element} 
                      onChange={e => handleElementChange(e.target.value)}
                    >
                      <option value="">-- Select Element --</option>
                      {availableElements.map(el => (
                        <option key={el} value={el}>{el}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="create-field-group">
                  <label>Element Classification Notes</label>
                  <input 
                    type="text" 
                    placeholder="Auto-populated description or custom element notes..." 
                    value={elementDescription}
                    onChange={e => setElementDescription(e.target.value)}
                  />
                </div>
              </div>

              {/* Section 4: Collection Notes & Curatorial Details */}
              <div className="create-form-section">
                <div className="create-section-header">
                  <span className="section-step">4</span>
                  <h3>Curatorial & Collection Notes</h3>
                </div>

                <div className="create-grid-2">
                  <div className="create-field-group">
                    <label>Duplicate Specimen Count</label>
                    <input 
                      type="text" 
                      placeholder="no, 1, 2..." 
                      value={duplicate}
                      onChange={e => setDuplicate(e.target.value)}
                    />
                  </div>

                  <div className="create-field-group">
                    <label>Variety / Plate Error / Flaw</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Inverted watermark, color shift..." 
                      value={errorNotes}
                      onChange={e => setErrorNotes(e.target.value)}
                    />
                  </div>
                </div>

                <div className="create-field-group">
                  <label>Comprehensive Specimen Description</label>
                  <textarea 
                    rows="3"
                    placeholder="Detailed historical, physical, or personal collection notes..." 
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Modal Footer / Action Bar */}
          <div className="create-modal-footer">
            <button 
              type="button" 
              className="btn btn-secondary" 
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button 
              type="submit" 
              className="btn btn-create-submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className="spinner-sm"></span>
                  <span>{submitStep || 'Saving Specimen...'}</span>
                </>
              ) : (
                <>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  <span>Catalog & Create Card</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
