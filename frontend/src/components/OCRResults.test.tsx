import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { OCRResults } from './OCRResults';
import { OCRResult } from '../types';

const baseAadhaarResult: OCRResult = {
  raw_text: 'Government of India\nRavi Kumar\n3288 9587 2529\n',
  fields: {
    full_name: 'Ravi Kumar',
    document_number: '328895872529',
    nationality: 'INDIA',
    country: 'INDIA',
    date_of_birth: '15/08/1990',
    sex: 'M',
    document_type: 'AADHAAR',
  },
  confidence: 0.9,
  detected_lines: [],
};

describe('OCRResults', () => {
  it('masks the Aadhaar number in the structured field display, showing only the last 4 digits', () => {
    // Per UIDAI convention (and this app's own DPDP compliance dashboard,
    // which already documents identifier hashing as a real control): the
    // officer UI must not show a citizen's full 12-digit Aadhaar number in
    // plaintext.
    render(<OCRResults data={baseAadhaarResult} />);
    expect(screen.getByText('XXXX XXXX 2529')).toBeInTheDocument();
    expect(screen.queryByText('328895872529')).not.toBeInTheDocument();
  });

  it('leaves non-Aadhaar document numbers unmasked', () => {
    const passportResult: OCRResult = {
      ...baseAadhaarResult,
      fields: { ...baseAadhaarResult.fields, document_number: 'X1234567', document_type: 'PASSPORT' },
    };
    render(<OCRResults data={passportResult} />);
    expect(screen.getByText('X1234567')).toBeInTheDocument();
  });
});
