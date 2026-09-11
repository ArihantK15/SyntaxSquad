import React, { useState, useRef } from 'react';
import { api } from '../services/api';
import { ProcessingPipeline, PipelineStage } from '../components/ProcessingPipeline';
import {
  UploadCloud,
  FileText,
  Camera,
  Play,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  Layers,
  X,
  RefreshCw,
  Video,
  SlidersHorizontal,
  Flame
} from 'lucide-react';

interface ScreeningPageProps {
  onScreeningComplete: (caseId: string) => void;
}

const INITIAL_STAGES: PipelineStage[] = [
  { id: '1', name: 'Document Ingestion & Secure Normalization', status: 'pending' },
  { id: '2', name: 'Module 1: OCR Text & Field Extraction', status: 'pending' },
  { id: '3', name: 'Module 2: ICAO 9303 MRZ Parsing & Rules Validation', status: 'pending' },
  { id: '4', name: 'Module 3: Tamper AI (Error Level Analysis & Splicing)', status: 'pending' },
  { id: '5', name: 'Module 4: Biometric Face Verification', status: 'pending' },
  { id: '6', name: 'Module 5: Risk Engine Aggregation & Watchlist Query', status: 'pending' },
  { id: '7', name: 'Case File Compilation & Audit Trail Generation', status: 'pending' },
];

export const ScreeningPage: React.FC<ScreeningPageProps> = ({ onScreeningComplete }) => {
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docPreview, setDocPreview] = useState<string | null>(null);
  const [liveFaceFile, setLiveFaceFile] = useState<File | null>(null);
  const [liveFacePreview, setLiveFacePreview] = useState<string | null>(null);

  const [documentType, setDocumentType] = useState('Passport');
  const [country, setCountry] = useState('REPUBLIC OF UTOPIA');

  const [isProcessing, setIsProcessing] = useState(false);
  const [stages, setStages] = useState<PipelineStage[]>(INITIAL_STAGES);

  // Tampering options
  const [tamperOption, setTamperOption] = useState('photo_replaced');
  const [generatingSpecimen, setGeneratingSpecimen] = useState(false);

  // Live Webcam state
  const [showWebcam, setShowWebcam] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);

  const [isDraggingDoc, setIsDraggingDoc] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const faceInputRef = useRef<HTMLInputElement>(null);

  const setDoc = (file: File) => {
    setDocFile(file);
    setDocPreview(URL.createObjectURL(file));
  };

  const handleDocChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setDoc(e.target.files[0]);
    }
  };

  const handleDocDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingDoc(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) {
      setDoc(file);
    }
  };

  const handleFaceChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setLiveFaceFile(file);
      setLiveFacePreview(URL.createObjectURL(file));
    }
  };

  // Webcam Controls
  const startWebcam = async () => {
    try {
      setShowWebcam(true);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' }
      });
      mediaStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err: any) {
      alert(`Webcam access error: ${err.message || 'Camera unavailable. Please upload a photo or use auto-simulation.'}`);
      setShowWebcam(false);
    }
  };

  const stopWebcam = () => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    setShowWebcam(false);
  };

  const captureWebcamSnapshot = () => {
    if (!videoRef.current) return;
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth || 640;
    canvas.height = videoRef.current.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (blob) {
        const file = new File([blob], 'live_webcam_capture.jpg', { type: 'image/jpeg' });
        setLiveFaceFile(file);
        setLiveFacePreview(URL.createObjectURL(file));
      }
      stopWebcam();
    }, 'image/jpeg', 0.95);
  };

  const updateStage = (index: number, status: PipelineStage['status'], latency?: number, detail?: string) => {
    setStages((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], status, latencyMs: latency, detail };
      return next;
    });
  };

  // Generate synthetic specimen directly
  const handleGenerateSpecimen = async (mode: string) => {
    try {
      setGeneratingSpecimen(true);
      const res = await api.generateSpecimenDoc({
        mode,
        surname: mode === 'photo_replaced' ? 'DOE' : 'KAUL',
        given_names: mode === 'photo_replaced' ? 'JOHN' : 'ARIHANT',
        doc_number: mode === 'mrz_tampered' ? 'P8892144' : 'X1234567',
        country_name: country
      });

      // Fetch the generated specimen blob so it can be screened as a real File upload
      const imgRes = await fetch(res.url);
      const blob = await imgRes.blob();
      const file = new File([blob], res.filename, { type: 'image/jpeg' });

      setDocFile(file);
      setDocPreview(res.url);
    } catch (err: any) {
      alert(`Specimen generator error: ${err.message}`);
    } finally {
      setGeneratingSpecimen(false);
    }
  };

  // Run full staged screening pipeline
  const handleStartScreening = async () => {
    if (!docFile) {
      alert('Please upload or generate a document first.');
      return;
    }

    try {
      setIsProcessing(true);
      setStages(INITIAL_STAGES.map((s) => ({ ...s, status: 'pending', latencyMs: undefined })));

      // Step 1: Upload
      updateStage(0, 'running');
      const t0 = performance.now();
      const uploadRes = await api.uploadScreeningDocument(docFile, documentType, country);
      const caseId = uploadRes.case_id;
      updateStage(0, 'completed', performance.now() - t0, `Case #${uploadRes.case_number} registered`);

      // Step 2: OCR
      updateStage(1, 'running');
      const t1 = performance.now();
      const ocrRes = await api.runStepOCR(caseId);
      updateStage(1, 'completed', performance.now() - t1, `Extracted ${ocrRes.ocr_result.detected_lines?.length || 0} text lines`);

      // Step 3: MRZ & Rules
      updateStage(2, 'running');
      const t2 = performance.now();
      const valRes = await api.runStepValidate(caseId);
      const mrzValid = valRes.mrz_result?.is_valid;
      updateStage(2, 'completed', performance.now() - t2, mrzValid ? 'All MRZ check digits verified' : 'Checksum discrepancy identified');

      // Step 4: Tamper AI
      updateStage(3, 'running');
      const t3 = performance.now();
      const tamperRes = await api.runStepTamper(caseId);
      const risk = tamperRes.tamper_result.risk_level;
      updateStage(3, 'completed', performance.now() - t3, `Forensic ELA completed: ${risk} Tamper Risk`);

      // Step 5: Face Verification
      updateStage(4, 'running');
      const t4 = performance.now();
      const faceRes = await api.runStepFace(caseId, liveFaceFile || undefined);
      updateStage(4, 'completed', performance.now() - t4, `Face Match: ${Math.round(faceRes.face_result.similarity * 100)}% (${faceRes.face_result.status})`);

      // Step 6: Risk Aggregation
      updateStage(5, 'running');
      const t5 = performance.now();
      const riskRes = await api.runStepRisk(caseId);
      updateStage(5, 'completed', performance.now() - t5, `Risk Score: ${Math.round(riskRes.risk_score)}/100 (${riskRes.risk_level})`);

      // Step 7: Finalize & Navigate
      updateStage(6, 'running');
      await new Promise((r) => setTimeout(r, 600));
      updateStage(6, 'completed', 100, 'Case file ready for officer inspection');

      // Transition to Case File
      setTimeout(() => {
        onScreeningComplete(caseId);
      }, 900);
    } catch (err: any) {
      alert(`Screening pipeline error: ${err.message}`);
      setIsProcessing(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold font-mono text-slate-100 tracking-wider">
          DOCUMENT SCREENING & INGESTION
        </h1>
        <p className="text-xs font-mono text-slate-400 mt-1">
          Upload physical document or generate controlled forensic test specimen for real-time AI inspection
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Upload & Specimen Generator */}
        <div className="lg:col-span-7 space-y-5">
          {/* Specimen Generator Bar */}
          <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3 shadow-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-cyan-300 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                Specimen Generator (SIH Evaluation Utility)
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                1-CLICK SYNTHETIC INGESTION
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {/* Button 1: Generate Genuine */}
              <button
                type="button"
                onClick={() => handleGenerateSpecimen('genuine')}
                disabled={generatingSpecimen || isProcessing}
                className="px-4 py-2.5 rounded-lg bg-slate-950 border border-emerald-500/40 hover:border-emerald-400 hover:bg-emerald-950/20 text-xs font-mono text-emerald-300 font-semibold transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Generate Genuine Demo</span>
              </button>

              {/* Button 2: Generate Tampered with dropdown option */}
              <div className="flex rounded-lg overflow-hidden border border-rose-500/40 bg-slate-950">
                <select
                  value={tamperOption}
                  onChange={(e) => setTamperOption(e.target.value)}
                  disabled={generatingSpecimen || isProcessing}
                  className="bg-slate-950 text-slate-200 px-2 py-1.5 text-xs font-mono focus:outline-none flex-1 min-w-0 border-r border-slate-800"
                >
                  <option value="photo_replaced">Photo Replacement</option>
                  <option value="mrz_tampered">MRZ Checksum Corruption</option>
                  <option value="altered_text">Altered Date/Text</option>
                  <option value="expired">Expired Document</option>
                  <option value="stamp_manipulated">Pasted Stamp Patch</option>
                  <option value="brightness_manipulated">Brightness Hotspot</option>
                  <option value="multiple_anomalies">Multiple Anomalies</option>
                </select>

                <button
                  type="button"
                  onClick={() => handleGenerateSpecimen(tamperOption)}
                  disabled={generatingSpecimen || isProcessing}
                  className="px-3 py-1.5 bg-rose-950/60 hover:bg-rose-900/60 text-rose-300 text-xs font-mono font-semibold transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50 shrink-0 whitespace-nowrap"
                  title="Generate Tampered Demo"
                >
                  <Flame className="w-3.5 h-3.5 text-rose-400" />
                  <span>Generate</span>
                </button>
              </div>
            </div>
          </div>

          {/* Document Upload Area */}
          <div className="p-5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <FileText className="w-4 h-4 text-cyan-400" />
              1. Document Specimen
            </h3>

            <input
              type="file"
              ref={fileInputRef}
              onChange={handleDocChange}
              accept="image/jpeg,image/png,image/jpg"
              className="hidden"
            />

            <div
              data-testid="doc-dropzone"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setIsDraggingDoc(true); }}
              onDragLeave={() => setIsDraggingDoc(false)}
              onDrop={handleDocDrop}
              className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                isDraggingDoc
                  ? 'border-cyan-400 bg-cyan-950/30'
                  : docPreview
                  ? 'border-cyan-500/50 bg-slate-950/80'
                  : 'border-slate-700 hover:border-cyan-400/50 bg-slate-950/40 hover:bg-slate-950/60'
              }`}
            >
              {docPreview ? (
                <div className="space-y-3">
                  <img
                    src={docPreview}
                    alt="Document Preview"
                    className="max-h-52 mx-auto rounded-lg border border-slate-800 object-contain shadow-md"
                  />
                  <span className="text-xs font-mono text-cyan-300 block">
                    Click to replace document image
                  </span>
                </div>
              ) : (
                <div className="space-y-2 py-4">
                  <UploadCloud className="w-10 h-10 text-cyan-400 mx-auto" />
                  <p className="text-sm font-mono text-slate-200 font-semibold">
                    Drop travel document here or click to browse
                  </p>
                  <p className="text-xs font-mono text-slate-400">
                    Supports JPG, JPEG, PNG (Normalized up to 1600px)
                  </p>
                </div>
              )}
            </div>

            {/* Document Metadata Form */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
                  Document Type
                </label>
                <select
                  value={documentType}
                  onChange={(e) => setDocumentType(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  <option value="Passport">Passport (TD3)</option>
                  <option value="National ID">National ID (TD1)</option>
                  <option value="Visa">Travel Visa</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
                  Issuing Jurisdiction
                </label>
                <select
                  value={country}
                  onChange={(e) => setCountry(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  <option value="REPUBLIC OF UTOPIA">REPUBLIC OF UTOPIA (UTO)</option>
                  <option value="DEMO STATE">DEMO STATE (DEM)</option>
                  <option value="ATLANTIS FEDERATION">ATLANTIS FEDERATION (ATL)</option>
                  <option value="INDIA">INDIA (IND)</option>
                  <option value="UNITED KINGDOM">UNITED KINGDOM (GBR)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Live Face Capture: Webcam in browser or File upload */}
          <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Camera className="w-4 h-4 text-cyan-400" />
                2. Live Traveler Face Capture
              </h3>
              <span className="text-[10px] font-mono text-slate-400">
                {liveFacePreview ? 'Biometric Loaded' : 'Auto-simulated if empty'}
              </span>
            </div>

            <input
              type="file"
              ref={faceInputRef}
              onChange={handleFaceChange}
              accept="image/jpeg,image/png,image/jpg"
              className="hidden"
            />

            {/* In-Browser Webcam Viewport if active */}
            {showWebcam ? (
              <div className="p-3 rounded-xl bg-slate-950 border border-cyan-500/50 space-y-3">
                <div className="relative rounded-lg overflow-hidden bg-black aspect-[4/3] max-h-64 mx-auto flex items-center justify-center">
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="w-full h-full object-cover mirror"
                  />
                  {/* Facial positioning reticle */}
                  <div className="absolute inset-0 border-2 border-cyan-400/40 rounded-full m-8 pointer-events-none flex items-center justify-center">
                    <span className="text-[10px] font-mono text-cyan-300 bg-black/60 px-2 py-0.5 rounded">
                      Align Face in Frame
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-center gap-3">
                  <button
                    type="button"
                    onClick={captureWebcamSnapshot}
                    className="px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono font-bold flex items-center gap-1.5 cursor-pointer shadow-md"
                  >
                    <Camera className="w-3.5 h-3.5" />
                    <span>Snap Photo</span>
                  </button>

                  <button
                    type="button"
                    onClick={stopWebcam}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-4">
                {liveFacePreview ? (
                  <div className="w-20 h-20 rounded-lg overflow-hidden bg-slate-950 border border-slate-700 shrink-0">
                    <img src={liveFacePreview} alt="Live face" className="w-full h-full object-cover" />
                  </div>
                ) : (
                  <div className="w-20 h-20 rounded-lg bg-slate-950 border border-dashed border-slate-800 flex items-center justify-center shrink-0">
                    <Camera className="w-6 h-6 text-slate-400" />
                  </div>
                )}

                <div className="space-y-2 flex-1">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={startWebcam}
                      className="px-3 py-1.5 rounded-lg bg-cyan-950/80 border border-cyan-500/40 hover:bg-cyan-900/60 text-xs font-mono text-cyan-300 font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <Video className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Capture from Webcam</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => faceInputRef.current?.click()}
                      className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 hover:border-slate-500 text-xs font-mono text-slate-300 transition-colors cursor-pointer"
                    >
                      {liveFacePreview ? 'Replace Photo' : 'Upload File'}
                    </button>
                  </div>
                  <p className="text-[11px] text-slate-400 font-mono">
                    Take a live camera picture or upload an image to test document portrait comparison.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Action Button */}
          <button
            onClick={handleStartScreening}
            disabled={!docFile || isProcessing}
            className="w-full bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-mono font-bold text-sm tracking-wider uppercase py-3.5 rounded-xl shadow-lg shadow-cyan-950/40 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-current" />
            <span>Execute Full AI Screening Pipeline</span>
          </button>
        </div>

        {/* Right Column: Live Processing Checklist */}
        <div className="lg:col-span-5">
          <ProcessingPipeline
            stages={stages}
            title={isProcessing ? 'Active Screening In-Flight' : 'Staged Pipeline Execution'}
          />
        </div>
      </div>
    </div>
  );
};
