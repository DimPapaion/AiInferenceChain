/**
 * ValidatorDashboard Component
 * 
 * Displays validator registration, status, and management
 */

import React, { useState, useEffect } from 'react';
import './ValidatorDashboard.css';

function ValidatorDashboard({ apiClient }) {
  const [validators, setValidators] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showRegisterForm, setShowRegisterForm] = useState(false);
  const [registerForm, setRegisterForm] = useState({
    address: '',
    name: '',
    email: '',
    stake_amount: 32.0,
  });
  const [registrationStatus, setRegistrationStatus] = useState(null);
  const [filter, setFilter] = useState('all');

  // Fetch validators
  useEffect(() => {
    fetchValidators();
    const interval = setInterval(fetchValidators, 5000);
    return () => clearInterval(interval);
  }, [filter]);

  const fetchValidators = async () => {
    try {
      setLoading(true);
      const status = filter === 'all' ? null : filter;
      const data = await apiClient.listValidators(status);
      setValidators(data);
    } catch (err) {
      console.error('Failed to fetch validators:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterChange = (e) => {
    const { name, value } = e.target;
    setRegisterForm(prev => ({
      ...prev,
      [name]: name === 'stake_amount' ? parseFloat(value) : value,
    }));
  };

  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    setRegistrationStatus({ type: 'loading', message: 'Registering validator...' });

    try {
      const result = await apiClient.registerValidator(registerForm);
      setRegistrationStatus({
        type: 'success',
        message: `✓ Validator registered: ${result.validator_id}`,
      });
      setRegisterForm({
        address: '',
        name: '',
        email: '',
        stake_amount: 32.0,
      });
      setShowRegisterForm(false);
      
      // Refresh validators
      setTimeout(fetchValidators, 1000);
    } catch (err) {
      setRegistrationStatus({
        type: 'error',
        message: `✗ Registration failed: ${err.message}`,
      });
    }
  };

  const handleConfirmStake = async (validatorId) => {
    try {
      await apiClient.confirmStake(validatorId);
      fetchValidators();
    } catch (err) {
      console.error('Failed to confirm stake:', err);
      alert(`Error: ${err.message}`);
    }
  };

  const getStatusBadge = (status) => {
    const badges = {
      pending: '⏳',
      active: '✅',
      inactive: '⏸️',
      slashed: '⚠️',
      exiting: '🚪',
    };
    return badges[status] || '?';
  };

  return (
    <div className="validator-dashboard">
      {/* Header with Register Button */}
      <div className="dashboard-header">
        <h2>Validator Management</h2>
        <button
          className="btn btn-primary"
          onClick={() => setShowRegisterForm(!showRegisterForm)}
        >
          {showRegisterForm ? '− Close' : '+ Register Validator'}
        </button>
      </div>

      {/* Registration Form */}
      {showRegisterForm && (
        <div className="register-form-card">
          <h3>Register New Validator</h3>
          <form onSubmit={handleRegisterSubmit}>
            <div className="form-group">
              <label htmlFor="address">Node Address</label>
              <input
                id="address"
                type="text"
                name="address"
                placeholder="validator1.localhost:50051"
                value={registerForm.address}
                onChange={handleRegisterChange}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="name">Validator Name</label>
              <input
                id="name"
                type="text"
                name="name"
                placeholder="Node Operator 1"
                value={registerForm.name}
                onChange={handleRegisterChange}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                name="email"
                placeholder="operator@example.com"
                value={registerForm.email}
                onChange={handleRegisterChange}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="stake">Stake Amount (IC tokens)</label>
              <input
                id="stake"
                type="number"
                name="stake_amount"
                min="32"
                step="0.1"
                value={registerForm.stake_amount}
                onChange={handleRegisterChange}
                required
              />
              <small>Minimum: 32.0 IC tokens</small>
            </div>

            {registrationStatus && (
              <div className={`status-message ${registrationStatus.type}`}>
                {registrationStatus.message}
              </div>
            )}

            <button type="submit" className="btn btn-success">
              Register Validator
            </button>
          </form>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="filter-tabs">
        {['all', 'active', 'pending', 'inactive', 'slashed'].map(status => (
          <button
            key={status}
            className={`filter-tab ${filter === status ? 'active' : ''}`}
            onClick={() => setFilter(status)}
          >
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      {/* Validators List */}
      <div className="validators-list">
        {loading ? (
          <div className="loading-state">Loading validators...</div>
        ) : validators.length === 0 ? (
          <div className="empty-state">
            <p>No validators found</p>
            <button className="btn btn-small" onClick={() => setShowRegisterForm(true)}>
              Register one now →
            </button>
          </div>
        ) : (
          <div className="validators-grid">
            {validators.map(validator => (
              <div key={validator.validator_id} className="validator-card">
                <div className="card-header">
                  <div className="validator-title">
                    <span className="status-badge">{getStatusBadge(validator.status)}</span>
                    <h3>{validator.name}</h3>
                  </div>
                  <span className="status-label">{validator.status}</span>
                </div>

                <div className="card-body">
                  <div className="info-row">
                    <span className="label">Address:</span>
                    <code>{validator.address}</code>
                  </div>

                  <div className="info-row">
                    <span className="label">Email:</span>
                    <span>{validator.email}</span>
                  </div>

                  <div className="info-row">
                    <span className="label">Stake:</span>
                    <strong>{validator.stake.toFixed(2)} IC</strong>
                  </div>

                  <div className="stats-row">
                    <div className="stat">
                      <span className="stat-label">Models Validated</span>
                      <span className="stat-value">{validator.models_validated}</span>
                    </div>
                    <div className="stat">
                      <span className="stat-label">Blocks Proposed</span>
                      <span className="stat-value">{validator.blocks_proposed}</span>
                    </div>
                    <div className="stat">
                      <span className="stat-label">Rewards</span>
                      <span className="stat-value">{validator.rewards_earned.toFixed(2)}</span>
                    </div>
                  </div>

                  {validator.status === 'pending' && (
                    <div className="pending-info">
                      <p>⏳ Waiting for on-chain stake confirmation</p>
                      <button
                        className="btn btn-small btn-success"
                        onClick={() => handleConfirmStake(validator.validator_id)}
                      >
                        Confirm Stake
                      </button>
                    </div>
                  )}
                </div>

                <div className="card-footer">
                  <small>Joined: {new Date(validator.joined_at).toLocaleDateString()}</small>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default ValidatorDashboard;
