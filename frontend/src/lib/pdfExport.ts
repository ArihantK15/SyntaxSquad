import React from 'react';
import { createRoot } from 'react-dom/client';
import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas-pro';
import { CaseDetail, DocumentAnalysis, RiskFactorContribution } from '../types';
import { CaseReportPrintable } from '../components/CaseReportPrintable';

interface GenerateArgs {
  caseData: CaseDetail;
  analysis?: DocumentAnalysis;
  riskBreakdown: RiskFactorContribution[];
  docImgUrl?: string;
}

/**
 * Renders CaseReportPrintable off-screen, rasterizes it, and downloads it as
 * a paginated PDF. Runs entirely client-side -- no backend endpoint needed --
 * since every value it needs is already loaded into the case detail page.
 */
export async function downloadCaseReportPdf({ caseData, analysis, riskBreakdown, docImgUrl }: GenerateArgs): Promise<void> {
  const container = document.createElement('div');
  container.style.position = 'fixed';
  container.style.top = '0';
  container.style.left = '-99999px';
  document.body.appendChild(container);

  const root = createRoot(container);
  root.render(
    React.createElement(CaseReportPrintable, { caseData, analysis, riskBreakdown, docImgUrl })
  );

  try {
    // Let React commit, then wait for every image (document/face crops) to
    // finish loading before rasterizing -- html2canvas snapshots whatever is
    // in the DOM at call time, so a still-loading <img> would print blank.
    await new Promise((resolve) => setTimeout(resolve, 50));
    const images = Array.from(container.querySelectorAll('img'));
    await Promise.all(
      images.map((img) =>
        img.complete
          ? Promise.resolve()
          : new Promise((resolve) => {
              img.onload = resolve;
              img.onerror = resolve;
            })
      )
    );

    const target = container.firstElementChild as HTMLElement;
    const canvas = await html2canvas(target, {
      scale: 1.5,
      backgroundColor: '#FFFFFF',
      useCORS: true
    });

    const pdf = new jsPDF({ orientation: 'portrait', unit: 'pt', format: 'a4' });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const imgWidth = pageWidth;
    const imgHeight = (canvas.height * imgWidth) / canvas.width;

    // JPEG rather than PNG: this is a photo-heavy report, and PNG's
    // lossless encoding of the two face crops and document photo alone was
    // producing 10MB+ files for a single-page report.
    const imgData = canvas.toDataURL('image/jpeg', 0.85);

    // A few points of overflow past one page shouldn't spawn a near-blank
    // second page -- tolerate a small overshoot before paginating.
    const overflowTolerance = 24;

    if (imgHeight <= pageHeight + overflowTolerance) {
      pdf.addImage(imgData, 'JPEG', 0, 0, imgWidth, imgHeight);
    } else {
      // Content taller than one page: slice the source canvas into
      // page-height chunks and add each as its own page, rather than
      // scaling the whole report down to fit (which would make small text
      // illegible).
      let renderedHeight = 0;
      const pageHeightPx = (pageHeight * canvas.width) / imgWidth;

      while (renderedHeight < canvas.height) {
        const sliceHeightPx = Math.min(pageHeightPx, canvas.height - renderedHeight);
        const sliceCanvas = document.createElement('canvas');
        sliceCanvas.width = canvas.width;
        sliceCanvas.height = sliceHeightPx;
        const ctx = sliceCanvas.getContext('2d')!;
        ctx.drawImage(canvas, 0, renderedHeight, canvas.width, sliceHeightPx, 0, 0, canvas.width, sliceHeightPx);

        const sliceImgData = sliceCanvas.toDataURL('image/jpeg', 0.85);
        const sliceImgHeight = (sliceHeightPx * imgWidth) / canvas.width;

        if (renderedHeight > 0) pdf.addPage();
        pdf.addImage(sliceImgData, 'JPEG', 0, 0, imgWidth, sliceImgHeight);

        renderedHeight += sliceHeightPx;
      }
    }

    pdf.save(`${caseData.case_number}_screening_report.pdf`);
  } finally {
    root.unmount();
    document.body.removeChild(container);
  }
}
