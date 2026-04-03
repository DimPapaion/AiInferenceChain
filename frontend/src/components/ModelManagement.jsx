/**
 * ModelManagement Component
 * 
 * Displays model registry, upload interface, and validation history
 */

import React, { useState, useEffect } from 'react';
import './ModelManagement.css';

function ModelManagement({ apiClient }) {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadForm, setUploadForm] = useState({
    name: '',
    version: '',
    framework: 'pytorch',
    description: '',
    input_shape: '[3, 224, 224]',
    output_shape: '[1000]',
    min_accuracy: 0.7,
    max_latency_ms: 100,
    max_size_mb: 200,
  });
  const [uploadStatus, setUploadStatus] = useState(null);
  const [filter, setFilter] = useState('all');
  const [selectedModel, setSelectedModel] = useState(null);
  const [modelValidations, setModelValidations] = useState([]);

  // Fetch models
  useEffect(() => {
    fetchModels();
    const interval = setInterval(fetchModels, 5000);
    return () => clearInterval(interval);
  }, [filter]);

  const fetchModels = async () => {
    try {
      setLoading(true);
      const state = filter === 'all' ? null : filter;
      const data = await apiClient.listModels(state);
      setModels(data);
    } catch (err) {
      console.error('Failed to fetch models:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadFormChange = (e) => {
    const { name, value } = e.target;
    setUploadForm(prev => ({
      ...prev,
      [name]: name.includes('accuracy') || name.includes('latency') || name.includes('size')
        ? parseFloat(value)
        : value,
    }));
  };

  const handleFileChange = (e) => {
    const file = e.target.files ? e.target.files[0] : null;
    setUploadFile(file);
  };

  const handleUploadSubmit = async (e) => {
    e.preventDefault();

    if (!uploadFile) {
      setUploadStatus({ type: 'error', message: 'Please select a model file' });
      return;
    }

    setUploadStatus({ type: 'loading', message: 'Uploading and validating model...' });

    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('name', uploadForm.name);
      formData.append('version', uploadForm.version);
      formData.append('framework', uploadForm.framework);
      formData.append('description', uploadForm.description);
      formData.append('input_shape', uploadForm.input_shape);
      formData.append('output_shape', uploadForm.output_shape);
      formData.append('min_accuracy', uploadForm.min_accuracy);
      formData.append('max_latency_ms', uploadForm.max_latency_ms);
      formData.append('max_size_mb', uploadForm.max_size_mb);

      const result = await apiClient.uploadModel(formData);

      setUploadStatus({
        type: result.status === 'approved' ? 'success' : 'warning',
        message: `${result.status === 'approved' ? '✓' : '⚠️'} ${result.message}`,
      });

      // Reset form
      setUploadFile(null);
      setUploadForm({
        name: '',
        version: '',
        framework: 'pytorch',
        description: '',
        input_shape: '[3, 224, 224]',
        output_shape: '[1000]',
        min_accuracy: 0.7,
        max_latency_ms: 100,
        max_size_mb: 200,
      });

      // Refresh models
      setTimeout(fetchModels, 1000);
    } catch (err) {
      setUploadStatus({
        type: 'error',
        message: `✗ Upload failed: ${err.message}`,
      });
    }
  };

  const handleViewValidations = async (modelId) => {
    try {
      const validations = await apiClient.getModelValidations(modelId);
      setSelectedModel(modelId);
      setModelValidations(validations);
    } catch (err) {
      console.error('Failed to fetch validations:', err);
    }
  };

  const getStateBadge = (state) => {
    const badges = {
      draft: '📝',
      validating: '⏳',
      approved: '✅',
      rejected: '❌',
      deprecated: '🔄',
      archived: '📦',
    };
    return badges[state] || '?';
  };

  return (
    <div className="model-management">
      {/* Header with Upload Button */}
      <div className="dashboard-header">
        <h2>Model Registry</h2>
        <button
          className="btn btn-primary"
          onClick={() => setShowUploadForm(!showUploadForm)}
        >
          {showUploadForm ? '− Close' : '+ Upload Model'}
        </button>
      </div>

      {/* Upload Form */}
      {showUploadForm && (
        <div className="upload-form-card">
          <h3>Upload New Model</h3>
          <form onSubmit={handleUploadSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="name">Model Name</label>
                <input
                  id="name"
                  type="text"
                  name="name"
                  placeholder="ResNet-50"
                  value={uploadForm.name}
                  onChange={handleUploadFormChange}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="version">Version</label>
                <input
                  id="version"
                  type="text"
                  name="version"
                  placeholder="1.0.0"
                  value={uploadForm.version}
                  onChange={handleUploadFormChange}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="framework">Framework</label>
                <select
                  id="framework"
                  name="framework"
                  value={uploadForm.framework}
                  onChange={handleUploadFormChange}
                >
                  <option value="pytorch">PyTorch</option>
                  <option value="tensorflow">TensorFlow</option>
                  <option value="onnx">ONNX</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                name="description"
                rows="3"
                placeholder="Model description and use case..."
                value={uploadForm.description}
                onChange={handleUploadFormChange}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="input_shape">Input Shape (JSON)</label>
                <input
                  id="input_shape"
                  type="text"
                  name="input_shape"
                  value={uploadForm.input_shape}
                  onChange={handleUploadFormChange}
                />
              </div>

              <div className="form-group">
                <label htmlFor="output_shape">Output Shape (JSON)</label>
                <input
                  id="output_shape"
                  type="text"
                  name="output_shape"
                  value={uploadForm.output_shape}
                  onChange={handleUploadFormChange}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="min_accuracy">Min Accuracy</label>
                <input
                  id="min_accuracy"
                  type="number"
                  name="min_accuracy"
                  min="0"
                  max="1"
                  step="0.01"
                  value={uploadForm.min_accuracy}
                  onChange={handleUploadFormChange}
                />
              </div>

              <div className="form-group">
                <label htmlFor="max_latency_ms">Max Latency (ms)</label>
                <input
                  id="max_latency_ms"
                  type="number"
                  name="max_latency_ms"
                  min="0"
                  step="10"
                  value={uploadForm.max_latency_ms}
                  onChange={handleUploadFormChange}
                />
              </div>

              <div className="form-group">
                <label htmlFor="max_size_mb">Max Size (MB)</label>
                <input
                  id="max_size_mb"
                  type="number"
                  name="max_size_mb"
                  min="0"
                  step="10"
                  value={uploadForm.max_size_mb}
                  onChange={handleUploadFormChange}
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="file">Model File</label>
              <input
                id="file"
                type="file"
                onChange={handleFileChange}
                accept=".pth,.pb,.onnx"
                required
              />
              {uploadFile && <small>Selected: {uploadFile.name}</small>}
            </div>

            {uploadStatus && (
              <div className={`status-message ${uploadStatus.type}`}>
                {uploadStatus.message}
              </div>
            )}

            <button type="submit" className="btn btn-success">
              Upload Model
            </button>
          </form>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="filter-tabs">
        {['all', 'approved', 'validating', 'draft', 'rejected'].map(state => (
          <button
            key={state}
            className={`filter-tab ${filter === state ? 'active' : ''}`}
            onClick={() => setFilter(state)}
          >
            {state.charAt(0).toUpperCase() + state.slice(1)}
          </button>
        ))}
      </div>

      {/* Models List */}
      <div className="models-list">
        {loading ? (
          <div className="loading-state">Loading models...</div>
        ) : models.length === 0 ? (
          <div className="empty-state">
            <p>No models found</p>
            <button className="btn btn-small" onClick={() => setShowUploadForm(true)}>
              Upload one now →
            </button>
          </div>
        ) : (
          <div className="models-grid">
            {models.map(model => (
              <div key={model.model_id} className="model-card">
                <div className="card-header">
                  <div className="model-title">
                    <span className="state-badge">{getStateBadge(model.state)}</span>
                    <div>
                      <h3>{model.name}</h3>
                      <p className="version">v{model.version}</p>
                    </div>
                  </div>
                  <span className="framework-badge">{model.framework}</span>
                </div>

                <div className="card-body">
                  <p className="description">{model.description || 'No description'}</p>

                  <div className="info-row">
                    <span className="label">Author:</span>
                    <span>{model.author}</span>
                  </div>

                  <div className="stats-row">
                    <div className="stat">
                      <span className="stat-label">Validations</span>
                      <span className="stat-value">{model.validation_count}</span>
                    </div>
                    {model.avg_accuracy !== null && (
                      <div className="stat">
                        <span className="stat-label">Avg Accuracy</span>
                        <span className="stat-value">{(model.avg_accuracy * 100).toFixed(1)}%</span>
                      </div>
                    )}
                    {model.avg_latency_ms !== null && (
                      <div className="stat">
                        <span className="stat-label">Avg Latency</span>
                        <span className="stat-value">{model.avg_latency_ms.toFixed(1)}ms</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="card-footer">
                  <button
                    className="btn btn-small"
                    onClick={() => handleViewValidations(model.model_id)}
                  >
                    View Validations →
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Validations Modal */}
      {selectedModel && (
        <div className="modal-overlay" onClick={() => setSelectedModel(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Validation History</h3>
              <button className="btn-close" onClick={() => setSelectedModel(null)}>✕</button>
            </div>

            <div className="validations-list">
              {modelValidations.length === 0 ? (
                <p>No validations yet</p>
              ) : (
                modelValidations.map((val, idx) => (
                  <div key={idx} className="validation-item">
                    <div className="validation-header">
                      <span className={val.passed ? 'passed' : 'failed'}>
                        {val.passed ? '✓' : '✗'}
                      </span>
                      <span className="validator-id">{val.validator_id}</span>
                      <span className="timestamp">
                        {new Date(val.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <div className="validation-details">
                      <p>Checks: {val.checks_passed}/{val.checks_total}</p>
                      {val.errors.length > 0 && (
                        <div className="errors">
                          {val.errors.map((err, i) => (
                            <small key={i}>❌ {err}</small>
                          ))}
                        </div>
                      )}
                      {val.warnings.length > 0 && (
                        <div className="warnings">
                          {val.warnings.map((warn, i) => (
                            <small key={i}>⚠️ {warn}</small>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ModelManagement;
