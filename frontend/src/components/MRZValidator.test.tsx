import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MRZValidator } from './MRZValidator';

describe('MRZValidator', () => {
  it('shows a neutral "not applicable" state, not a warning, when the document type never has an MRZ by design', () => {
    // Reproduces a real UX bug: Aadhaar (and PAN/Driving Licence/Voter ID/
    // Visa) have no ICAO 9303 Machine Readable Zone by design -- an absent
    // MRZ on one of these is expected, not a failure, but the component
    // showed the same orange-warning "not detected" styling regardless of
    // document type, misleadingly implying something went wrong.
    render(<MRZValidator mrz={undefined} documentType="AADHAAR" />);
    expect(screen.getByText(/not applicable for this document type/i)).toBeInTheDocument();
    expect(screen.queryByText(/no machine readable zone.*detected or parsed/i)).not.toBeInTheDocument();
  });

  it('still shows the warning styling when a document type that SHOULD have an MRZ has none detected', () => {
    render(<MRZValidator mrz={undefined} documentType="PASSPORT" />);
    expect(screen.getByText(/no machine readable zone.*detected or parsed/i)).toBeInTheDocument();
    expect(screen.queryByText(/not applicable for this document type/i)).not.toBeInTheDocument();
  });

  it('defaults to the warning styling when document type is unknown, rather than assuming MRZ is inapplicable', () => {
    render(<MRZValidator mrz={undefined} />);
    expect(screen.getByText(/no machine readable zone.*detected or parsed/i)).toBeInTheDocument();
  });
});
