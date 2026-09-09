import os
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.utils.synthetic_generator import SyntheticDocumentGenerator

def generate_samples():
    output_dir = Path(__file__).resolve().parent.parent / "demo-data" / "samples"
    os.makedirs(output_dir, exist_ok=True)
    faces_dir = Path(__file__).resolve().parent.parent / "demo-data" / "faces"
    person_a = str(faces_dir / "person_a.jpg")
    person_b = str(faces_dir / "person_b.jpg")

    samples = [
        {
            "filename": "specimen_genuine.jpg",
            "mode": "genuine",
            "surname": "KAUL",
            "given": "ARIHANT",
            "country_name": "REPUBLIC OF UTOPIA",
            "code": "UTO",
            "doc_no": "X1234567",
            "dob": "000101",
            "exp": "300101"
        },
        {
            "filename": "specimen_mrz_tampered.jpg",
            "mode": "mrz_tampered",
            "surname": "SHARMA",
            "given": "PRIYA",
            "country_name": "REPUBLIC OF UTOPIA",
            "code": "UTO",
            "doc_no": "P8892144",
            "dob": "950512",
            "exp": "281115"
        },
        {
            "filename": "specimen_photo_replaced.jpg",
            "mode": "photo_replaced",
            "surname": "DOE",
            "given": "JOHN",
            "country_name": "DEMO STATE",
            "code": "DEM",
            "doc_no": "D5512398",
            "dob": "880320",
            "exp": "290814"
        },
        {
            "filename": "specimen_expired.jpg",
            "mode": "expired",
            "surname": "PATEL",
            "given": "ROHAN",
            "country_name": "REPUBLIC OF UTOPIA",
            "code": "UTO",
            "doc_no": "A9938210",
            "dob": "921010",
            "exp": "220101"
        },
        {
            "filename": "specimen_multiple_anomalies.jpg",
            "mode": "multiple_anomalies",
            "surname": "KOROL",
            "given": "VIKTOR",
            "country_name": "ATLANTIS FEDERATION",
            "code": "ATL",
            "doc_no": "P8892144",
            "dob": "850704",
            "exp": "270420"
        }
    ]

    print(f"[BorderMesh] Generating {len(samples)} offline judging specimen documents in {output_dir}...")
    for s in samples:
        out_file = output_dir / s["filename"]
        SyntheticDocumentGenerator.generate_document(
            out_path=str(out_file),
            mode=s["mode"],
            surname=s["surname"],
            given_names=s["given"],
            country_code=s["code"],
            country_name=s["country_name"],
            doc_number=s["doc_no"],
            dob_yymmdd=s["dob"],
            expiry_yymmdd=s["exp"],
            face_photo_path=person_a
        )
        print(f"  ✓ Created {s['filename']} ({s['mode']})")

    # Generate sample live portraits. sample_live_face.jpg is Person A (same
    # as every specimen's document photo) for testing a genuine MATCH;
    # sample_live_face_mismatch.jpg is Person B, for manually testing a
    # mismatch against specimen_photo_replaced.jpg / specimen_multiple_anomalies.jpg.
    live_out = output_dir / "sample_live_face.jpg"
    SyntheticDocumentGenerator.generate_live_face_image(str(live_out), face_photo_path=person_a)
    print(f"  ✓ Created sample_live_face.jpg")

    mismatch_out = output_dir / "sample_live_face_mismatch.jpg"
    SyntheticDocumentGenerator.generate_live_face_image(str(mismatch_out), face_photo_path=person_b)
    print(f"  ✓ Created sample_live_face_mismatch.jpg")
    print("[BorderMesh] Offline specimen generation complete.")

if __name__ == "__main__":
    generate_samples()
