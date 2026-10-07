import { X } from "lucide-react";

interface EmailFailureModalProps {
  isOpen: boolean;
  onClose: () => void;
  failures: Array<{
    investor_name: string;
    investor_email: string;
    error_message: string;
  }>;
}

export function EmailFailureModal({ isOpen, onClose, failures }: EmailFailureModalProps) {
  if (!isOpen) return null;

  return (
    <div className="modal d-block" role="dialog" style={{ background: 'rgba(0,0,0,0.6)' }}>
      <div className="modal-dialog modal-dialog-centered modal-lg" role="document">
        <div className="modal-content" style={{ background: 'var(--color-bg-surface)' }}>
          <div className="modal-header" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
            <h5 className="modal-title" style={{ color: '#00005b' }}>
              Email Delivery Failures
            </h5>
            <button type="button" className="btn" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
          <div className="modal-body" style={{ maxHeight: '400px', overflowY: 'auto' }}>
            {failures.length === 0 ? (
              <p style={{ color: 'var(--color-text-tertiary)' }}>No failed email deliveries found.</p>
            ) : (
              <table className="table table-dark mb-0">
                <thead>
                  <tr>
                    <th>Investor Name</th>
                    <th>Email Address</th>
                    <th>Error Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {failures.map((failure, index) => (
                    <tr key={index}>
                      <td>{failure.investor_name || '—'}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{failure.investor_email || '—'}</td>
                      <td style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {failure.error_message || 'Unknown error'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}